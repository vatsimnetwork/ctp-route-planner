import json
import re

from django.db.models.functions import Upper
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from routeplanner.models import HighlightedWaypoint, Location, CustomFix
from routeplanner.permissions import write_access_required
from routeplanner.views.routeplotter import check_for_oceanic_waypoint


def highlighted_waypoints_geojson(request):
    highlights = list(HighlightedWaypoint.objects.all())
    if not highlights:
        return JsonResponse({"type": "FeatureCollection", "features": []})

    # All identifiers are stored uppercase in HighlightedWaypoint
    identifiers = [hw.identifier for hw in highlights]
    hw_map = {hw.identifier: hw for hw in highlights}

    coord_map = {}

    # CustomFix identifiers are also uppercase — plain equality is fine
    for fix in CustomFix.objects.filter(identifier__in=identifiers):
        coord_map[fix.identifier] = (fix.longitude, fix.latitude)

    remaining = [i for i in identifiers if i not in coord_map]
    if remaining:
        # Location identifiers may be mixed-case in the DB, so compare via Upper()
        for loc in (
            Location.objects
            .annotate(identifier_upper=Upper('identifier'))
            .filter(identifier_upper__in=remaining)
        ):
            key = loc.identifier.upper()
            if key not in coord_map:
                coord_map[key] = (loc.longitude, loc.latitude)

    # Fall back to oceanic coordinate parsing for anything still unresolved
    for identifier in identifiers:
        if identifier not in coord_map:
            result = check_for_oceanic_waypoint(identifier)
            if result:
                coord_map[identifier] = (result[1], result[0])  # (lon, lat)

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
    entries = HighlightedWaypoint.objects.all()
    return render(request, 'highlightedwaypoints.html', {'entries': entries})


@write_access_required
@require_POST
def highlighted_waypoint_create(request):
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

    entry, created = HighlightedWaypoint.objects.update_or_create(
        identifier=identifier,
        defaults={'color': color, 'note': note},
    )

    return JsonResponse({
        'identifier': entry.identifier,
        'color': entry.color,
        'note': entry.note,
        'created': created,
    }, status=201 if created else 200)


@write_access_required
@require_POST
def highlighted_waypoint_delete(request, identifier):
    deleted, _ = HighlightedWaypoint.objects.filter(identifier=identifier.upper()).delete()
    if not deleted:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse({'deleted': identifier.upper()})
