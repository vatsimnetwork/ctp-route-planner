import json
import requests
from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from routeplanner.models import Location, Airway, AirwayWaypoint

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
    try:
        lat = float(waypoint.split("N")[0])
        lon= -float(waypoint.split("N")[1].split("W")[0])
        return lat,lon
    except:
        return False
    
def get_waypoint(waypoint_string: str, before_waypoint: Location):
    try:
        waypoints = Location.objects.filter(identifier=waypoint_string)
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
        airway = Airway.objects.get(identifier=airway_identifier)
        waypoints = airway.get_ordered_waypoints()
        entry_index = next(i for i, wp in enumerate(waypoints) if wp.identifier == entry_waypoint.identifier)
        exit_index = next(i for i, wp in enumerate(waypoints) if wp.identifier == exit_waypoint.identifier)
        if entry_index < exit_index:
            return [[wp.longitude, wp.latitude] for wp in waypoints[entry_index:exit_index + 1]]
        else:
            return [[wp.longitude, wp.latitude] for wp in reversed(waypoints[exit_index:entry_index + 1])]
    except Airway.DoesNotExist:
        return None


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
        tokens = line.split()
        resolved = []
        prev_location = None

        for token in tokens:
            oceanic = check_for_oceanic_waypoint(token)
            if oceanic:
                lat, lon = oceanic
                resolved.append({'type': 'waypoint', 'identifier': token, 'lon': lon, 'lat': lat, 'location': None})
                prev_location = None
                continue

            wp = get_waypoint(token, prev_location) if prev_location else Location.objects.filter(identifier=token).first()
            if wp:
                resolved.append({'type': 'waypoint', 'identifier': wp.identifier, 'lon': wp.longitude, 'lat': wp.latitude, 'location': wp})
                prev_location = wp
                continue

            if Airway.objects.filter(identifier=token).exists():
                resolved.append({'type': 'airway', 'identifier': token})
                continue

            resolved.append({'type': 'unknown', 'identifier': token})

        final_coords = []
        final_labels = []
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

        result.append({
            'coords': final_coords,
            'labels': final_labels,
            'unknown': [r['identifier'] for r in resolved if r['type'] == 'unknown'],
        })

    return JsonResponse({'routes': result})


