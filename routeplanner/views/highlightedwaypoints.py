import json
import logging
import re

from django.db.models.functions import Upper
from django.http import JsonResponse
from django.shortcuts import render

from routeplanner import api_client
from routeplanner.api_client import _stable_id_for_identifier, _waypoint_id
from routeplanner.models import Location
from routeplanner.permissions import write_access_required
from routeplanner.views.routeplotter import check_for_oceanic_waypoint

logger = logging.getLogger(__name__)


def highlighted_waypoints_geojson(request):
    try:
        highlights = api_client.list_highlighted_waypoints()
    except Exception:
        logger.exception("Failed to fetch highlighted waypoints from API")
        return JsonResponse({"type": "FeatureCollection", "features": []})

    if not highlights:
        return JsonResponse({"type": "FeatureCollection", "features": []})

    identifiers = [hw.identifier for hw in highlights]
    hw_map = {hw.identifier: hw for hw in highlights}

    coord_map = {}

    try:
        api_fixes = api_client.list_custom_fixes()
        fix_map = {f.identifier: f for f in api_fixes}
        for ident in identifiers:
            if ident in fix_map:
                f = fix_map[ident]
                coord_map[ident] = (f.longitude, f.latitude)
    except Exception:
        logger.exception("Failed to fetch custom fixes from API for highlighted waypoints")

    remaining = [i for i in identifiers if i not in coord_map]
    if remaining:
        for loc in (
            Location.objects
            .annotate(identifier_upper=Upper('identifier'))
            .filter(identifier_upper__in=remaining)
        ):
            key = loc.identifier.upper()
            if key not in coord_map:
                coord_map[key] = (loc.longitude, loc.latitude)

    for identifier in identifiers:
        if identifier not in coord_map:
            result = check_for_oceanic_waypoint(identifier)
            if result:
                coord_map[identifier] = (result[1], result[0])

    features = []
    for identifier, (lon, lat) in coord_map.items():
        hw = hw_map[identifier]
        features.append({
            "type": "Feature",
            "properties": {"identifier": identifier, "color": hw.color, "note": hw.note},
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})


@write_access_required
def highlighted_waypoints(request):
    try:
        entries = api_client.list_highlighted_waypoints()
    except Exception:
        logger.exception("Failed to fetch highlighted waypoints from API")
        entries = []
    return render(request, 'highlightedwaypoints.html', {'entries': entries})


@write_access_required
def highlighted_waypoint_create(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    identifier = (data.get('identifier') or '').strip().upper()
    color = (data.get('color') or '').strip()
    note = (data.get('note') or '').strip()

    if not identifier:
        return JsonResponse({'error': 'Identifier is required'}, status=400)
    if len(identifier) > 10:
        return JsonResponse({'error': 'Identifier must be 10 characters or fewer'}, status=400)
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        return JsonResponse({'error': 'Color must be a valid hex color (e.g. #ff0000)'}, status=400)

    waypoint_id = None
    latitude = None
    longitude = None

    try:
        api_fixes = api_client.list_custom_fixes()
        fix_map = {f.identifier: f for f in api_fixes}
        if identifier in fix_map:
            f = fix_map[identifier]
            waypoint_id = _stable_id_for_identifier(identifier)
            latitude = f.latitude
            longitude = f.longitude
    except Exception:
        pass

    if latitude is None:
        loc = (
            Location.objects
            .annotate(identifier_upper=Upper('identifier'))
            .filter(identifier_upper=identifier)
            .first()
        )
        if loc:
            waypoint_id = _waypoint_id(loc)
            latitude = loc.latitude
            longitude = loc.longitude

    if latitude is None:
        oceanic = check_for_oceanic_waypoint(identifier)
        if oceanic:
            lat, lon = oceanic
            waypoint_id = _stable_id_for_identifier(identifier)
            latitude = lat
            longitude = lon

    try:
        result = api_client.upsert_highlighted_waypoint(identifier, color, note, waypoint_id, latitude, longitude)
    except Exception:
        logger.exception("Failed to upsert highlighted waypoint via API")
        return JsonResponse({'error': 'Failed to save to data API'}, status=503)

    return JsonResponse({
        'identifier': result.get('identifier', identifier),
        'color': result.get('color', color),
        'note': result.get('note', note),
        'created': True,
    }, status=201)


@write_access_required
def highlighted_waypoint_delete(request, identifier):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        api_client.delete_highlighted_waypoint(identifier.upper())
    except Exception:
        logger.exception("Failed to delete highlighted waypoint via API")
        return JsonResponse({'error': 'Failed to delete from data API'}, status=503)

    return JsonResponse({'deleted': identifier.upper()})
