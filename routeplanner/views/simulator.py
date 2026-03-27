import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from routeplanner.models import Route
from routeplanner.views.routeplotter import (
    DIRECT_ROUTE_TOKENS,
    build_plotting_caches,
    check_for_oceanic_waypoint,
    normalize_route_text,
    resolve_token,
)

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def simulator_data(request):
    """
    Response:
    {
        "routes": [
            {
                "identifier": "EHAM_ERAKA",
                "routeString": "EHAM REKLO DCT ERAKA",
                "group": "EMEA",
                "color": "#ffffff",
                "enabled": true,
                "tags": ["TAG1"],
                "facilities": ["EHAA", "EGGX"],
                "locations": [
                    {"identifier": "EHAM", "latitude": 52.31, "longitude": 4.76},
                    ...
                ]
            },
            ...
        ]
    }
    """
    routes = list(Route.objects.order_by('group', 'identifier'))
    normalized_lines = [normalize_route_text(r.routestring) for r in routes]
    caches = build_plotting_caches(normalized_lines)

    result = []
    for route, normalized_line in zip(routes, normalized_lines):
        locations = []
        prev_location = None

        for token in normalized_line.split():
            token_upper = token.upper()

            if token_upper in DIRECT_ROUTE_TOKENS:
                continue

            oceanic = check_for_oceanic_waypoint(token_upper)
            if oceanic:
                lat, lon = oceanic
                locations.append({'identifier': token_upper, 'latitude': lat, 'longitude': lon})
                prev_location = None
                continue

            resolved = resolve_token(
                token_upper,
                prev_location,
                location_candidates_by_upper=caches['location_candidates_by_upper'],
                airway_by_upper=caches['airway_by_upper'],
                airway_waypoints_by_upper=caches['airway_waypoints_by_upper'],
            )
            if resolved and resolved['type'] == 'waypoint':
                locations.append({
                    'identifier': resolved['identifier'],
                    'latitude': resolved['lat'],
                    'longitude': resolved['lon'],
                })
                prev_location = resolved['waypoint']

        result.append({
            'identifier': route.identifier,
            'routeString': route.routestring,
            'group': route.group,
            'color': route.color,
            'enabled': route.enabled,
            'tags': route.tags.split() if route.tags else [],
            'facilities': route.facilities.split() if route.facilities else [],
            'locations': locations,
        })

    return JsonResponse({'routes': result})