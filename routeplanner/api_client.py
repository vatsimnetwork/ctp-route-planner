"""
CTP API Client for Django Route Planner
Handles communication with the .NET CTP-API for route management
"""

import requests
import logging
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class CTPAPIClient:
    """
    Client for communicating with CTP-API routes endpoints
    Provides methods to fetch, save, and delete routes with waypoint data
    """

    def __init__(self):
        raw_base_url = (getattr(settings, 'CTP_API_BASE_URL', 'http://localhost:5000/api') or '').strip()
        self.base_url = self._normalize_base_url(raw_base_url)
        self.timeout = getattr(settings, 'CTP_API_TIMEOUT', 30)
        self.api_key = getattr(settings, 'CTP_API_KEY', '')
        self.cache_ttl = getattr(settings, 'CTP_API_CACHE_TTL', 600)  # 10 minutes default
        self.routes_endpoint = f"{self.base_url}/routes"
        self.last_error = ''

    def _normalize_base_url(self, base_url: str) -> str:
        candidate = base_url or 'http://localhost:5000/api'
        if '://' not in candidate:
            candidate = f"http://{candidate}"
        candidate = candidate.rstrip('/')

        parsed = urlparse(candidate)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            logger.warning("Invalid CTP_API_BASE_URL '%s'. Falling back to default.", base_url)
            return 'http://localhost:5000/api'

        if not parsed.path or parsed.path == '/':
            candidate = f"{candidate}/api"
        return candidate

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with API key"""
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['X-API-Key'] = self.api_key
        return headers

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                     use_cache: bool = False, cache_key: Optional[str] = None) -> Optional[Dict]:
        """
        Make HTTP request to API with error handling
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: Full endpoint URL
            data: Request body data for POST/PUT
            use_cache: Whether to use/cache results
            cache_key: Cache key for storing results
            
        Returns:
            Response JSON or None on error
        """
        try:
            self.last_error = ''
            # Check cache for GET requests
            if use_cache and cache_key and method == 'GET':
                cached = cache.get(cache_key)
                if cached is not None:
                    logger.debug(f"Cache hit for {cache_key}")
                    return cached

            # Make request
            if method == 'GET':
                response = requests.get(endpoint, headers=self._get_headers(), timeout=self.timeout)
            elif method == 'POST':
                response = requests.post(endpoint, json=data, headers=self._get_headers(), timeout=self.timeout)
            elif method == 'DELETE':
                response = requests.delete(endpoint, headers=self._get_headers(), timeout=self.timeout)
            else:
                logger.error(f"Unsupported HTTP method: {method}")
                return None

            response.raise_for_status()
            result = response.json() if response.text else None

            # Cache successful GET responses
            if use_cache and cache_key and method == 'GET' and result:
                cache.set(cache_key, result, self.cache_ttl)
                logger.debug(f"Cached {cache_key}")

            return result

        except requests.exceptions.Timeout:
            self.last_error = f"Timeout calling {endpoint}"
            logger.error(self.last_error)
            # Try to return cached data on timeout
            if use_cache and cache_key:
                cached = cache.get(cache_key)
                if cached:
                    logger.warning(f"API timeout, returning cached data for {cache_key}")
                    return cached
            return None
        except requests.exceptions.ConnectionError:
            # Local Django runserver on Windows cannot always resolve host.docker.internal.
            # Retry once with localhost so the same env can work in both local and containerized runs.
            if 'host.docker.internal' in endpoint:
                fallback_endpoint = endpoint.replace('host.docker.internal', 'localhost')
                try:
                    if method == 'GET':
                        response = requests.get(fallback_endpoint, headers=self._get_headers(), timeout=self.timeout)
                    elif method == 'POST':
                        response = requests.post(fallback_endpoint, json=data, headers=self._get_headers(), timeout=self.timeout)
                    elif method == 'DELETE':
                        response = requests.delete(fallback_endpoint, headers=self._get_headers(), timeout=self.timeout)
                    else:
                        response = None

                    if response is not None:
                        response.raise_for_status()
                        result = response.json() if response.text else None
                        if use_cache and cache_key and method == 'GET' and result:
                            cache.set(cache_key, result, self.cache_ttl)
                        self.last_error = ''
                        return result
                except Exception:
                    pass

            self.last_error = f"Connection error calling {endpoint}"
            logger.error(self.last_error)
            return None
        except requests.exceptions.HTTPError as e:
            self.last_error = f"HTTP error {e.response.status_code}: {e.response.text}"
            logger.error(self.last_error)
            return None
        except Exception as e:
            self.last_error = f"Error calling {endpoint}: {str(e)}"
            logger.error(self.last_error)
            return None

    def get_routes(self) -> Optional[List[Dict]]:
        """
        Fetch all routes from API
        
        Returns:
            List of route dictionaries with waypoints, or None on error
        """
        cache_key = 'ctp_api:routes:all'
        result = self._make_request('GET', self.routes_endpoint, use_cache=True, cache_key=cache_key)
        
        if isinstance(result, list):
            return result
        return None

    def get_route(self, identifier: str) -> Optional[Dict]:
        """
        Fetch a specific route by identifier
        
        Args:
            identifier: Route identifier (e.g., "NAT-M")
            
        Returns:
            Route dictionary with waypoints, or None if not found
        """
        cache_key = f'ctp_api:route:{identifier}'
        endpoint = f"{self.routes_endpoint}/{identifier}"
        
        result = self._make_request('GET', endpoint, use_cache=True, cache_key=cache_key)
        return result if isinstance(result, dict) else None

    def save_route(self, route_data: Dict) -> Optional[Dict]:
        """
        Save or update a single route
        
        Args:
            route_data: Route data including:
                - identifier: str
                - routeString: str
                - group: str
                - color: str (optional)
                - enabled: bool (optional)
                - tags: List[str] (optional)
                - locations: List[{identifier, latitude, longitude, maximumAircraftPerHour}]
                
        Returns:
            Response with message and route ID, or None on error
        """
        result = self._make_request('POST', self.routes_endpoint, data=route_data)
        
        # Invalidate cache
        cache.delete('ctp_api:routes:all')
        cache.delete(f"ctp_api:route:{route_data.get('identifier')}")
        
        return result

    def save_routes_batch(self, routes: List[Dict]) -> Optional[Dict]:
        """
        Save multiple routes in a batch operation
        
        Args:
            routes: List of route data dictionaries
            
        Returns:
            Response with batch status, or None on error
        """
        endpoint = f"{self.routes_endpoint}/batch"
        result = self._make_request('POST', endpoint, data=routes)
        
        # Invalidate cache
        cache.delete('ctp_api:routes:all')
        for route in routes:
            cache.delete(f"ctp_api:route:{route.get('identifier')}")
        
        return result

    def delete_route(self, identifier: str) -> Optional[Dict]:
        """
        Delete a route by identifier
        
        Args:
            identifier: Route identifier
            
        Returns:
            Response with message, or None on error
        """
        endpoint = f"{self.routes_endpoint}/{identifier}"
        result = self._make_request('DELETE', endpoint)
        
        # Invalidate cache
        cache.delete('ctp_api:routes:all')
        cache.delete(f"ctp_api:route:{identifier}")
        
        return result

    def is_available(self) -> bool:
        """
        Check if API is available
        
        Returns:
            True if API is reachable, False otherwise
        """
        try:
            response = requests.get(
                self.routes_endpoint,
                headers=self._get_headers(),
                timeout=5  # Short timeout for availability check
            )
            return response.status_code < 500
        except Exception as e:
            logger.warning(f"API availability check failed: {str(e)}")
            return False

    def clear_cache(self):
        """Clear all route-related cache entries"""
        cache.delete('ctp_api:routes:all')
        logger.info("Cleared CTP API route cache")
