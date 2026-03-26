"""
Django views for route management via CTP-API
Routes are now stored and managed through the .NET API instead of local Django DB
"""

import json
import logging
from typing import Optional, Dict, Any, List

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from routeplanner.api_client import CTPAPIClient
from routeplanner.permissions import write_access_required

logger = logging.getLogger(__name__)

# Initialize API client
api_client = CTPAPIClient()


def _route_to_api_format(route_django: Dict) -> Dict:
    """
    Convert Django route format to CTP-API format
    
    Args:
        route_django: Route dict from Django form
        
    Returns:
        Route dict for API (RouteSegment format)
    """
    return {
        'identifier': route_django.get('identifier', ''),
        'routeString': route_django.get('routestring', ''),
        'group': route_django.get('group', ''),
        'color': route_django.get('color', ''),
        'enabled': route_django.get('enabled', True),
        'tags': (route_django.get('tags', '') or '').split(),
        'locations': route_django.get('locations', [])  # Waypoints from API
    }


def _api_route_to_django_format(route_api: Dict) -> Dict:
    """
    Convert CTP-API route format to Django display format
    
    Args:
        route_api: Route dict from API
        
    Returns:
        Route dict for Django template
    """
    return {
        'pk': route_api.get('identifier', ''),
        'identifier': route_api.get('identifier', ''),
        'group': route_api.get('group', ''),
        'routestring': route_api.get('routeString', ''),
        'facilities': '',  # Not used in new system
        'tags': ' '.join(route_api.get('tags', [])),
        'color': route_api.get('color', ''),
        'enabled': route_api.get('enabled', True),
        'waypoints': route_api.get('locations', []),  # Include waypoints for display
    }


def _sorted_routes_queryset():
    """Legacy - not used with API"""
    pass


def _normalize_token_text(value):
    """Normalize whitespace and separators in token text"""
    return ' '.join((value or '').replace(',', ' ').replace(';', ' ').split())


def _coerce_bool(value, default=None):
    """Convert value to boolean"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'true', '1', 'yes', 'on'}:
            return True
        if normalized in {'false', '0', 'no', 'off'}:
            return False
        return None
    if isinstance(value, (int, float)):
        return value == 1 if value != 0 else False
    return None


@require_http_methods(["GET"])
def routes(request):
    """
    Display all routes stored in CTP-API
    Routes are now fetched from the REST API instead of local DB
    """
    try:
        if not api_client.is_available():
            logger.warning("CTP-API not available, rendering empty routes")
            return render(request, 'routes.html', {
                'routes': [],
                'error': 'CTP-API is currently unavailable. Some features may be limited.',
                'current_revision_number': 0,
            })

        # Fetch routes from API
        routes_data = api_client.get_routes()
        
        if routes_data is None:
            logger.error("Failed to fetch routes from API")
            return render(request, 'routes.html', {
                'routes': [],
                'error': 'Failed to load routes from CTP-API',
                'current_revision_number': 0,
            })

        # Convert API format to Django template format
        routes_list = [_api_route_to_django_format(r) for r in routes_data]
        routes_list.sort(key=lambda r: (r['group'], r['identifier']))

        return render(request, 'routes.html', {
            'routes': routes_list,
            'current_revision_number': 0,  # Revision tracking handled by API
            'api_source': True,
        })

    except Exception as e:
        logger.exception("Error in routes view")
        return render(request, 'routes.html', {
            'routes': [],
            'error': f'Error loading routes: {str(e)}',
            'current_revision_number': 0,
        })


@write_access_required
@require_http_methods(["POST"])
def routes_save(request):
    """
    Save route changes to CTP-API
    
    Expects JSON payload with:
    {
        "updates": [
            {
                "pk": "OLD_IDENTIFIER",
                "identifier": "NEW_IDENTIFIER",
                "routestring": "ROUTE STRING",
                "group": "GROUP",
                "tags": "TAG1 TAG2",
                "color": "#ff0000",
                "enabled": true,
                "locations": [{identifier, latitude, longitude, maximumAircraftPerHour}, ...]
            }
        ],
        "deletes": [...]
    }
    """
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    raw_updates = payload.get('updates', [])
    raw_deletes = payload.get('deletes', [])

    if not raw_updates and not raw_deletes:
        return JsonResponse({'success': True, 'message': 'No changes to save.'})

    try:
        # Handle deletions
        for route_data in raw_deletes:
            identifier = (route_data.get('pk') or '').strip()
            if not identifier:
                return JsonResponse({'error': 'Delete identifier is required'}, status=400)

            result = api_client.delete_route(identifier)
            if result is None:
                return JsonResponse({'error': f"Failed to delete route '{identifier}'"}, status=500)

        # Handle updates/creates
        saved_routes = []
        for route_data in raw_updates:
            identifier = (route_data.get('identifier') or '').strip().upper()
            routestring = _normalize_token_text(route_data.get('routestring'))
            group = (route_data.get('group') or '').strip()
            tags = _normalize_token_text(route_data.get('tags') or '')
            color = (route_data.get('color') or '').strip()
            enabled = _coerce_bool(route_data.get('enabled'), default=True)
            locations = route_data.get('locations', [])

            # Validate
            if not identifier:
                return JsonResponse({'error': 'Route identifier is required'}, status=400)
            if not routestring:
                return JsonResponse({'error': 'Route string is required'}, status=400)
            if not isinstance(enabled, bool):
                return JsonResponse({'error': 'Enabled must be true or false'}, status=400)

            # Prepare API payload
            api_route = {
                'identifier': identifier,
                'routeString': routestring,
                'group': group,
                'color': color,
                'enabled': enabled,
                'tags': tags.split() if tags else [],
                'locations': locations,
            }

            # Save to API
            result = api_client.save_route(api_route)
            if result is None:
                return JsonResponse({'error': f"Failed to save route '{identifier}'"}, status=500)

            saved_routes.append({
                'pk': identifier,
                'identifier': identifier,
                'group': group,
                'routestring': routestring,
                'tags': tags,
                'color': color,
                'enabled': enabled,
            })

        return JsonResponse({
            'success': True,
            'saved_routes': saved_routes,
            'revision_number': 0,  # Revisions handled by API
            'message': f'Saved {len(saved_routes)} route(s)'
        })

    except Exception as e:
        logger.exception("Error in routes_save")
        return JsonResponse({'error': f'Error saving routes: {str(e)}'}, status=500)


@write_access_required
@require_http_methods(["POST"])
def route_delete(request, identifier):
    """
    Delete a specific route from CTP-API
    
    Expects JSON payload with original route values for conflict detection
    """
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    identifier = identifier.strip().upper()

    try:
        result = api_client.delete_route(identifier)
        
        if result is None:
            return JsonResponse(
                {'error': f"Route '{identifier}' not found or already deleted"},
                status=404
            )

        return JsonResponse({'success': True})

    except Exception as e:
        logger.exception(f"Error deleting route {identifier}")
        return JsonResponse({'error': f'Error deleting route: {str(e)}'}, status=500)