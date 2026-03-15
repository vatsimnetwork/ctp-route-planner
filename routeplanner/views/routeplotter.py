import requests
from django.shortcuts import render
from django.http import JsonResponse
from routeplanner.models import Location

def index(request):
    return render(request, 'routeplotter.html')

def fir_geojson(request):
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