import json
import logging

from django.http import JsonResponse
from django.shortcuts import render

from routeplanner import api_client
from routeplanner.permissions import write_access_required

logger = logging.getLogger(__name__)


def custom_fixes(request):
    try:
        fixes = api_client.list_custom_fixes()
    except Exception:
        logger.exception("Failed to fetch custom fixes from API")
        fixes = []
    return render(request, 'customfixes.html', {'fixes': fixes})


@write_access_required
def custom_fix_create(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    identifier = (data.get('identifier') or '').strip().upper()
    note = (data.get('note') or '').strip()

    if not identifier:
        return JsonResponse({'error': 'Identifier is required'}, status=400)
    if len(identifier) > 10:
        return JsonResponse({'error': 'Identifier must be 10 characters or fewer'}, status=400)

    try:
        latitude = float(data['latitude'])
        longitude = float(data['longitude'])
    except (KeyError, TypeError, ValueError):
        return JsonResponse({'error': 'Valid latitude and longitude are required'}, status=400)

    if not (-90 <= latitude <= 90):
        return JsonResponse({'error': 'Latitude must be between -90 and 90'}, status=400)
    if not (-180 <= longitude <= 180):
        return JsonResponse({'error': 'Longitude must be between -180 and 180'}, status=400)

    try:
        result = api_client.upsert_custom_fix(identifier, latitude, longitude, note)
    except Exception:
        logger.exception("Failed to upsert custom fix via API")
        return JsonResponse({'error': 'Failed to save to data API'}, status=503)

    return JsonResponse({
        'id': result.get('id', 0),
        'identifier': result.get('identifier', identifier),
        'latitude': result.get('latitude', latitude),
        'longitude': result.get('longitude', longitude),
        'note': result.get('note', note),
        'created': True,
    }, status=201)


@write_access_required
def custom_fix_delete(request, identifier):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        api_client.delete_custom_fix(identifier.upper())
    except Exception:
        logger.exception("Failed to delete custom fix via API")
        return JsonResponse({'error': 'Failed to delete from data API'}, status=503)

    return JsonResponse({'deleted': identifier.upper()})
