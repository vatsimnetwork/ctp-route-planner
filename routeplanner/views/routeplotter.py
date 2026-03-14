import requests
from django.shortcuts import render
from django.http import JsonResponse

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