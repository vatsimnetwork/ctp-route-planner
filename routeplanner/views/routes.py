import json
import logging
import re

from django.http import JsonResponse
from django.shortcuts import render

from routeplanner import api_client
from routeplanner.discord import notify_routes_changed
from routeplanner.permissions import WRITE_ROLES, write_access_required
from routeplanner.views.routeplotter import build_plotting_caches, normalize_route_text

logger = logging.getLogger(__name__)


def _normalize_token_text(value):
    return ' '.join((value or '').replace(',', ' ').replace(';', ' ').split())


def _normalize_tags(value):
    """Normalize and sort tags so comparison is order-independent."""
    return ' '.join(sorted(_normalize_token_text(value).split()))


def _coerce_bool(value, default=None):
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
        if value == 1:
            return True
        if value == 0:
            return False
    return None


def _serialize_route(route_ns):
    return {
        'pk': route_ns.identifier,
        'identifier': route_ns.identifier,
        'group': route_ns.group,
        'routestring': route_ns.routestring,
        'facilities': route_ns.facilities,
        'tags': route_ns.tags,
        'color': route_ns.color,
        'enabled': route_ns.enabled,
    }


def _validate_route_payload(route_data, require_original=False, require_current_values=True):
    identifier = (route_data.get('identifier') or '').strip().upper()
    group = (route_data.get('group') or '').strip()
    routestring = _normalize_token_text(route_data.get('routestring'))
    facilities = _normalize_token_text(route_data.get('facilities'))
    tags = _normalize_token_text(route_data.get('tags'))
    color = (route_data.get('color') or '').strip()
    enabled = _coerce_bool(route_data.get('enabled'), default=True)
    original = route_data.get('original') or {}

    if not isinstance(enabled, bool):
        return None, 'Enabled must be true or false.'

    if require_current_values and not identifier:
        return None, 'Identifier is required.'
    if require_current_values and not routestring:
        return None, 'Route string is required.'
    if require_current_values and re.search(r'[^A-Za-z0-9 ]', routestring):
        return None, 'Route string contains invalid characters. Only letters, digits, and spaces are allowed.'
    if require_current_values and re.search(r'[^A-Za-z0-9 ]', facilities):
        return None, 'Facilities contains invalid characters. Only letters, digits, and spaces are allowed.'
    if require_current_values and re.search(r'[^A-Za-z0-9 ]', tags):
        return None, 'Tags contains invalid characters. Only letters, digits, and spaces are allowed.'
    if color and not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        return None, 'Color must be a valid hex color (e.g. #ff0000) or empty.'

    validated = {
        'pk': (route_data.get('pk') or '').strip(),
        'api_id': route_data.get('api_id', 0),
        'identifier': identifier,
        'group': group,
        'routestring': routestring,
        'facilities': facilities,
        'tags': tags,
        'color': color,
        'enabled': enabled,
        'original': {
            'pk': (original.get('pk') or '').strip(),
            'group': (original.get('group') or '').strip(),
            'routestring': _normalize_token_text(original.get('routestring')),
            'facilities': _normalize_token_text(original.get('facilities')),
            'tags': _normalize_tags(original.get('tags')),
            'color': (original.get('color') or '').strip(),
            'enabled': _coerce_bool(original.get('enabled'), default=True),
        },
    }

    if validated['original']['enabled'] is None:
        return None, 'Original enabled value must be true or false.'

    if require_original and not validated['original']['pk']:
        return None, 'Original route reference is missing.'

    return validated, None


def _get_current_event_id():
    event_id = api_client.get_latest_event_id()
    if event_id is None:
        raise ValueError("No events exist in ctp-api. Create an event first.")
    return event_id


def routes(request):
    try:
        event_id = _get_current_event_id()
        route_list = api_client.list_routes(event_id)
        route_list.sort(key=lambda r: (r.group, r.identifier))
        revision_number = api_client.latest_revision_number()
    except Exception:
        logger.exception("Failed to fetch routes from API")
        route_list = []
        revision_number = 0

    has_write_access = bool(WRITE_ROLES.intersection(request.user_roles))
    return render(request, 'routes.html', {
        'routes': route_list,
        'current_revision_number': revision_number,
        'has_write_access': has_write_access,
    })


@write_access_required
def route_delete(request, identifier):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        event_id = _get_current_event_id()
        current_routes = api_client.list_routes(event_id)
    except Exception:
        logger.exception("Failed to fetch routes from API")
        return JsonResponse({'error': 'Failed to reach data API'}, status=503)

    route = next((r for r in current_routes if r.identifier == identifier), None)
    if route is None:
        return JsonResponse({'success': True})

    try:
        payload = json.loads(request.body or '{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    original = payload.get('original') or {}
    original_pk = (original.get('pk') or '').strip()
    original_routestring = _normalize_token_text(original.get('routestring'))
    original_group = (original.get('group') or '').strip()
    original_facilities = _normalize_token_text(original.get('facilities'))
    original_tags = _normalize_tags(original.get('tags'))
    original_color = (original.get('color') or '').strip()
    original_enabled = _coerce_bool(original.get('enabled'), default=True)

    if not isinstance(original_enabled, bool):
        return JsonResponse({'error': 'Original enabled value must be true or false.'}, status=400)

    if not original_pk or original_pk != identifier:
        return JsonResponse({'error': 'Original route reference is missing.'}, status=400)

    if (
        _normalize_token_text(route.routestring) != original_routestring
        or (route.group or '').strip() != original_group
        or _normalize_token_text(route.facilities) != original_facilities
        or _normalize_tags(route.tags) != original_tags
        or (route.color or '').strip() != original_color
        or route.enabled != original_enabled
    ):
        return JsonResponse({'error': f"Conflict: route '{original_pk}' was changed by another user."}, status=409)

    try:
        api_client.batch_save_routes(event_id, updates=[], deletes=[route.api_id])
        api_client.create_route_revision(event_id)
    except Exception:
        logger.exception("Failed to delete route via API")
        return JsonResponse({'error': 'Failed to save to data API'}, status=503)

    notify_routes_changed(f"deleted '{identifier}'")
    return JsonResponse({'success': True})


@write_access_required
def routes_save(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body or '{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    raw_updates = payload.get('updates', [])
    raw_deletes = payload.get('deletes', [])

    updates = []
    for route_data in raw_updates:
        validated, error = _validate_route_payload(route_data)
        if error:
            return JsonResponse({'error': error}, status=400)
        updates.append(validated)

    deletes = []
    for route_data in raw_deletes:
        validated, error = _validate_route_payload(route_data, require_original=True, require_current_values=False)
        if error:
            return JsonResponse({'error': error}, status=400)
        deletes.append(validated)

    if not updates and not deletes:
        return JsonResponse({'success': True, 'message': 'No changes to save.'})

    try:
        event_id = _get_current_event_id()
        current_routes = api_client.list_routes(event_id)
    except Exception:
        logger.exception("Failed to fetch routes from API")
        return JsonResponse({'error': 'Failed to reach data API'}, status=503)

    routes_by_identifier = {r.identifier: r for r in current_routes}
    reserved_identifiers = {r.identifier for r in current_routes}

    delete_ids = []
    for route_data in deletes:
        original = route_data['original']
        route = routes_by_identifier.get(original['pk'])
        if route is None:
            return JsonResponse({'error': f"Conflict: route '{original['pk']}' no longer exists."}, status=409)
        if (
            _normalize_token_text(route.routestring) != original['routestring']
            or (route.group or '').strip() != original['group']
            or _normalize_token_text(route.facilities) != original['facilities']
            or _normalize_tags(route.tags) != original['tags']
            or (route.color or '').strip() != original['color']
            or route.enabled != original['enabled']
        ):
            return JsonResponse({'error': f"Conflict: route '{original['pk']}' was changed by another user."}, status=409)

        delete_ids.append(route.api_id)
        reserved_identifiers.discard(route.identifier)
        del routes_by_identifier[route.identifier]

    try:
        next_revision = api_client.latest_revision_number() + 1
    except Exception:
        next_revision = 0

    segment_updates = []
    saved_routes = []
    for route_data in updates:
        current_identifier = route_data['pk']
        original = route_data['original']
        api_id = route_data.get('api_id', 0)

        if current_identifier:
            route = routes_by_identifier.get(current_identifier)
            if route is None:
                return JsonResponse({'error': f"Conflict: route '{current_identifier}' no longer exists."}, status=409)
            api_id = route.api_id
            if (
                _normalize_token_text(route.routestring) != original['routestring']
                or (route.group or '').strip() != original['group']
                or _normalize_token_text(route.facilities) != original['facilities']
                or _normalize_tags(route.tags) != original['tags']
                or (route.color or '').strip() != original['color']
                or route.enabled != original['enabled']
            ):
                return JsonResponse({'error': f"Conflict: route '{current_identifier}' was changed by another user."}, status=409)
        else:
            api_id = 0

        new_identifier = route_data['identifier']
        taken = reserved_identifiers - ({current_identifier} if current_identifier else set())
        if new_identifier in taken:
            return JsonResponse({'error': f"Identifier '{new_identifier}' is already in use."}, status=400)

        if current_identifier and new_identifier != current_identifier:
            delete_ids.append(api_id)
            reserved_identifiers.discard(current_identifier)
            routes_by_identifier.pop(current_identifier, None)
            api_id = 0

        seg = api_client.route_to_segment_payload(route_data, api_id, event_id, route_revision=next_revision)
        segment_updates.append(seg)
        reserved_identifiers.add(new_identifier)


        saved_routes.append({
            'pk': new_identifier,
            'identifier': new_identifier,
            'group': route_data['group'],
            'routestring': route_data['routestring'],
            'facilities': route_data['facilities'],
            'tags': route_data['tags'],
            'color': route_data['color'],
            'enabled': route_data['enabled'],
        })

    all_normalized = [normalize_route_text(rd['routestring']) for rd in updates]
    try:
        caches = build_plotting_caches(all_normalized)
    except Exception:
        logger.exception("Failed to build plotting caches for location resolution")
        caches = {}

    for seg, route_data in zip(segment_updates, updates):
        normalized = normalize_route_text(route_data['routestring'])
        try:
            seg['locations'] = api_client.resolve_route_to_locations(normalized, caches)
        except Exception:
            logger.exception("Failed to resolve locations for route %s", route_data.get('identifier'))
            seg['locations'] = []

    try:
        api_client.batch_save_routes(event_id, updates=segment_updates, deletes=delete_ids)
        revision_number = api_client.create_route_revision(event_id)
    except Exception:
        logger.exception("Failed to save routes via API")
        return JsonResponse({'error': 'Failed to save to data API'}, status=503)

    if saved_routes:
        notify_routes_changed(f"saved {len(saved_routes)} route(s)")
    return JsonResponse({'success': True, 'saved_routes': saved_routes, 'revision_number': revision_number})
