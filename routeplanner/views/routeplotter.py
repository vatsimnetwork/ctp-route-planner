import json
import re
import requests
from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from routeplanner.models import Location, Airway, AirwayWaypoint, Route

DIRECT_ROUTE_TOKENS = {'DCT', 'DIRECT'}

def index(request):
    return render(request, 'routeplotter.html')

def fir_geojson(request):
    local_path = settings.FIR_BOUNDARIES_PATH
    if local_path.exists():
        try:
            data = json.loads(local_path.read_bytes())
            return JsonResponse(data)
        except (json.JSONDecodeError, OSError):
            pass

    url = "https://raw.githubusercontent.com/vatsimnetwork/vatspy-data-project/master/Boundaries.geojson"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return JsonResponse(response.json())
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
def waypoints_geojson(request):
    try:
        min_lon = float(request.GET['minLon'])
        min_lat = float(request.GET['minLat'])
        max_lon = float(request.GET['maxLon'])
        max_lat = float(request.GET['maxLat'])
    except (KeyError, ValueError):
        return JsonResponse({"type": "FeatureCollection", "features": []}, status=400)

    waypoints = Location.objects.filter(
        longitude__gte=min_lon, longitude__lte=max_lon,
        latitude__gte=min_lat,  latitude__lte=max_lat,
    )
    features = [{
        "type": "Feature",
        "properties": {"identifier": wp.identifier},
        "geometry": {"type": "Point", "coordinates": [wp.longitude, wp.latitude]},
    } for wp in waypoints]
    return JsonResponse({"type": "FeatureCollection", "features": features})

def check_for_oceanic_waypoint(waypoint: str):
    token = (waypoint or '').strip().upper()
    if not token:
        return False

    m = re.fullmatch(r'(\d{1,2}(?:\.\d{1,2})?)([NS])(\d{1,3}(?:\.\d{1,2})?)([EW])', token)
    if m:
        lat = float(m.group(1))
        lon = float(m.group(3))
        if m.group(2) == 'S':
            lat = -lat
        if m.group(4) == 'W':
            lon = -lon
        return lat, lon

   
    m = re.fullmatch(r'(\d{2})(\d{2})([NSEW])', token)
    if m:
        lat_mag = float(m.group(1))
        lon_mag = float(m.group(2))
        quadrant = m.group(3)

        if quadrant == 'N':
            return lat_mag, -lon_mag
        if quadrant == 'E':
            return lat_mag, lon_mag
        if quadrant == 'S':
            return -lat_mag, lon_mag
        return -lat_mag, -lon_mag  

    m = re.fullmatch(r'(\d{2})([NS])(\d{2})', token)
    if m:
        lat_mag = float(m.group(1))
        lon_mag = 100.0 + float(m.group(3))
        lat = lat_mag if m.group(2) == 'N' else -lat_mag
        lon = -lon_mag if m.group(2) == 'N' else lon_mag
        return lat, lon

    m = re.fullmatch(r'(\d{2})([EW])(\d{2})', token)
    if m:
        lat_mag = float(m.group(1))
        lon_mag = 100.0 + float(m.group(3))
        if m.group(2) == 'E':
            return lat_mag, lon_mag
        return -lat_mag, -lon_mag

    m = re.fullmatch(r'H(\d{2})(\d{2})', token)
    if m:
        lat = float(m.group(1)) + 0.5
        lon = -float(m.group(2))
        return lat, lon

    return False


def normalize_route_text(value: str) -> str:
    return ' '.join((value or '').replace(',', ' ').replace(';', ' ').split())
    
def get_waypoint(waypoint_string: str, before_waypoint: Location):
    try:
        waypoints = Location.objects.filter(identifier__iexact=waypoint_string)
        if len(waypoints) == 0:
            return None
        if len(waypoints) == 1:
            return waypoints[0]
        return min(
            waypoints,
            key=lambda wp: (wp.latitude - before_waypoint.latitude) ** 2
                        + (wp.longitude - before_waypoint.longitude) ** 2
        ) 
    except Location.DoesNotExist:
        return None
    
def get_airway_coordinates(airway_identifier: str, entry_waypoint: Location, exit_waypoint: Location):
    try:
        airway = Airway.objects.get(identifier__iexact=airway_identifier)
        waypoints = airway.get_ordered_waypoints()
        entry_index = next(i for i, wp in enumerate(waypoints) if wp.identifier == entry_waypoint.identifier)
        exit_index = next(i for i, wp in enumerate(waypoints) if wp.identifier == exit_waypoint.identifier)
        if entry_index < exit_index:
            return [[wp.longitude, wp.latitude] for wp in waypoints[entry_index:exit_index + 1]]
        else:
            return [[wp.longitude, wp.latitude] for wp in reversed(waypoints[exit_index:entry_index + 1])]
    except (Airway.DoesNotExist, StopIteration):
        return None


def calculate_distance_squared(wp: Location, ref_wp: Location) -> float:
    """Calculate squared distance between two waypoints (avoids sqrt)"""
    return (wp.latitude - ref_wp.latitude) ** 2 + (wp.longitude - ref_wp.longitude) ** 2


def resolve_token(token_upper: str, prev_location: Location = None):
    """
    Resolve a token to either a waypoint or airway.
    If both exist with the same name, return the one that's closer.
    
    Returns: dict with 'type', and either 'waypoint' or 'airway' data
    """
    # First try to get waypoint(s)
    waypoints = Location.objects.filter(identifier__iexact=token_upper)
    airway = Airway.objects.filter(identifier__iexact=token_upper).first()
    
    # No waypoint or airway found
    if not waypoints.exists() and not airway:
        return None
    
    # Only waypoint exists
    if waypoints.exists() and not airway:
        if len(waypoints) == 1:
            wp = waypoints[0]
        else:
            # Multiple waypoints with same name - choose closest
            wp = min(
                waypoints,
                key=lambda w: calculate_distance_squared(w, prev_location) if prev_location else 0
            )
        return {
            'type': 'waypoint',
            'waypoint': wp,
            'identifier': wp.identifier,
            'lon': wp.longitude,
            'lat': wp.latitude
        }
    
    # Only airway exists
    if not waypoints.exists() and airway:
        return {
            'type': 'airway',
            'airway': airway,
            'identifier': airway.identifier
        }
    
    # Both exist - choose the closer one
    # For waypoint, use its coordinates
    # For airway, use the first waypoint's coordinates
    if prev_location:
        # Get closest waypoint from the waypoints list
        closest_waypoint = min(
            waypoints,
            key=lambda w: calculate_distance_squared(w, prev_location)
        )
        waypoint_distance = calculate_distance_squared(closest_waypoint, prev_location)
        
        # Get first waypoint of airway as entry point
        airway_first_wp = airway.get_ordered_waypoints().first()
        if airway_first_wp:
            airway_distance = calculate_distance_squared(airway_first_wp, prev_location)
        else:
            airway_distance = float('inf')
        
        # Choose the closer one
        if waypoint_distance <= airway_distance:
            return {
                'type': 'waypoint',
                'waypoint': closest_waypoint,
                'identifier': closest_waypoint.identifier,
                'lon': closest_waypoint.longitude,
                'lat': closest_waypoint.latitude
            }
        else:
            return {
                'type': 'airway',
                'airway': airway,
                'identifier': airway.identifier
            }
    else:
        # No previous location to compare - prefer waypoint
        if waypoints.exists():
            wp = waypoints.first()
            return {
                'type': 'waypoint',
                'waypoint': wp,
                'identifier': wp.identifier,
                'lon': wp.longitude,
                'lat': wp.latitude
            }
        else:
            return {
                'type': 'airway',
                'airway': airway,
                'identifier': airway.identifier
            }


def plot_route(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    route_text = data.get('route', '')
    lines = [l.strip() for l in route_text.split('\n') if l.strip()]

    result = []
    for line in lines:
        normalized_line = normalize_route_text(line)
        route_obj = Route.objects.filter(identifier__iexact=normalized_line).first()
        if route_obj is None:
            route_obj = Route.objects.filter(routestring__iexact=normalized_line).first()
        route_group = route_obj.group if route_obj else ''
        route_tokens = normalized_line.split()
        
        resolved = []
        prev_location = None

        for token in route_tokens:
            token_clean = token.strip()
            token_upper = token_clean.upper()

            # ICAO routes may include DCT as a separator for a direct leg.
            if token_upper in DIRECT_ROUTE_TOKENS:
                continue

            oceanic = check_for_oceanic_waypoint(token_upper)
            if oceanic:
                lat, lon = oceanic
                resolved.append({'type': 'waypoint', 'identifier': token_upper, 'lon': lon, 'lat': lat, 'location': None})
                prev_location = None
                continue

            # Use the new resolve_token function that handles both waypoints and airways
            resolved_item = resolve_token(token_upper, prev_location)
            if resolved_item:
                if resolved_item['type'] == 'waypoint':
                    resolved.append({
                        'type': 'waypoint',
                        'identifier': resolved_item['identifier'],
                        'lon': resolved_item['lon'],
                        'lat': resolved_item['lat'],
                        'location': resolved_item['waypoint']
                    })
                    prev_location = resolved_item['waypoint']
                else:  # airway
                    resolved.append({
                        'type': 'airway',
                        'identifier': resolved_item['identifier']
                    })
                continue

            resolved.append({'type': 'unknown', 'identifier': token_clean})

        final_coords = []
        final_labels = []
        unresolved_tokens = []
        for i, item in enumerate(resolved):
            if item['type'] == 'waypoint':
                final_coords.append([item['lon'], item['lat']])
                final_labels.append({'identifier': item['identifier'], 'lon': item['lon'], 'lat': item['lat']})
            elif item['type'] == 'airway':
                prev_item = next((r for r in reversed(resolved[:i]) if r['type'] == 'waypoint' and r.get('location')), None)
                next_item = next((r for r in resolved[i + 1:] if r['type'] == 'waypoint' and r.get('location')), None)
                if prev_item and next_item:
                    airway_coords = get_airway_coordinates(item['identifier'], prev_item['location'], next_item['location'])
                    if airway_coords:
                        final_coords.extend(airway_coords[1:-1])
                    else:
                        unresolved_tokens.append(item['identifier'])
                else:
                    unresolved_tokens.append(item['identifier'])

        result.append({
            'group': route_group,
            'coords': final_coords,
            'labels': final_labels,
            'unknown': [r['identifier'] for r in resolved if r['type'] == 'unknown'] + unresolved_tokens,
        })

    return JsonResponse({'routes': result})


