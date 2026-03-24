import json
import re

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render

from routeplanner.discord import notify_routes_changed
from routeplanner.models import Route, RouteRevisionEntry, RouteRevisionSet
from routeplanner.permissions import write_access_required


def _sorted_routes_queryset():
    return Route.objects.order_by('group', 'identifier')


def _latest_revision_number():
    latest_revision = RouteRevisionSet.objects.order_by('-number').first()
    return latest_revision.number if latest_revision else 0


def _create_revision_snapshot(routes_queryset):
    latest_revision = RouteRevisionSet.objects.select_for_update().order_by('-number').first()
    next_revision_number = (latest_revision.number if latest_revision else 0) + 1
    revision = RouteRevisionSet.objects.create(number=next_revision_number)
    RouteRevisionEntry.objects.bulk_create([
        RouteRevisionEntry(
            revision=revision,
            identifier=route.identifier,
            group=route.group,
            routestring=route.routestring,
            facilities=route.facilities,
            tags=route.tags,
            color=route.color,
        )
        for route in routes_queryset
    ])
    return revision.number


def _normalize_token_text(value):
    return ' '.join((value or '').replace(',', ' ').replace(';', ' ').split())


def _serialize_route(route):
    return {
        'pk': route.identifier,
        'identifier': route.identifier,
        'group': route.group,
        'routestring': route.routestring,
        'facilities': route.facilities,
        'tags': route.tags,
        'color': route.color,
    }


def _validate_route_payload(route_data, require_original=False, require_current_values=True):
    identifier = (route_data.get('identifier') or '').strip().upper()
    group = (route_data.get('group') or '').strip()
    routestring = _normalize_token_text(route_data.get('routestring'))
    facilities = _normalize_token_text(route_data.get('facilities'))
    tags = _normalize_token_text(route_data.get('tags'))
    color = (route_data.get('color') or '').strip()
    original = route_data.get('original') or {}

    if require_current_values and not identifier:
        return None, 'Identifier is required.'
    if require_current_values and not routestring:
        return None, 'Route string is required.'
    if require_current_values and (',' in routestring or ';' in routestring):
        return None, 'Commas and semicolons are not allowed in route strings.'
    if require_current_values and (',' in facilities or ';' in facilities):
        return None, 'Commas and semicolons are not allowed in facilities.'
    if require_current_values and (',' in tags or ';' in tags):
        return None, 'Commas and semicolons are not allowed in tags.'
    if color and not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        return None, 'Color must be a valid hex color (e.g. #ff0000) or empty.'

    validated = {
        'pk': (route_data.get('pk') or '').strip(),
        'identifier': identifier,
        'group': group,
        'routestring': routestring,
        'facilities': facilities,
        'tags': tags,
        'color': color,
        'original': {
            'pk': (original.get('pk') or '').strip(),
            'group': (original.get('group') or '').strip(),
            'routestring': _normalize_token_text(original.get('routestring')),
            'facilities': _normalize_token_text(original.get('facilities')),
            'tags': _normalize_token_text(original.get('tags')),
            'color': (original.get('color') or '').strip(),
        },
    }

    if require_original and not validated['original']['pk']:
        return None, 'Original route reference is missing.'

    return validated, None


def routes(request):
    route_list = _sorted_routes_queryset()
    return render(request, 'routes.html', {
        'routes': route_list,
        'current_revision_number': _latest_revision_number(),
    })


@write_access_required
@transaction.atomic
def route_delete(request, identifier):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body or '{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    original = payload.get('original') or {}
    original_pk = (original.get('pk') or '').strip()
    original_routestring = (original.get('routestring') or '').strip()
    original_group = (original.get('group') or '').strip()
    original_facilities = _normalize_token_text(original.get('facilities'))
    original_tags = _normalize_token_text(original.get('tags'))
    original_color = (original.get('color') or '').strip()

    if not original_pk or original_pk != identifier:
        return JsonResponse({'error': 'Original route reference is missing.'}, status=400)

    try:
        route = Route.objects.select_for_update().get(identifier=identifier)
    except Route.DoesNotExist:
        # Already gone — treat as success
        return JsonResponse({'success': True})

    if (
        route.routestring != _normalize_token_text(original_routestring)
        or route.group != original_group
        or route.facilities != original_facilities
        or route.tags != original_tags
        or route.color != original_color
    ):
        return JsonResponse({'error': f"Conflict: route '{original_pk}' was changed by another user."}, status=409)

    route.delete()
    notify_routes_changed(f"deleted '{identifier}'")
    return JsonResponse({'success': True})


@write_access_required
@transaction.atomic
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

    existing_routes = list(Route.objects.select_for_update().all())
    routes_by_identifier = {route.identifier: route for route in existing_routes}
    reserved_identifiers = {route.identifier for route in existing_routes}

    for route_data in deletes:
        original = route_data['original']
        route = routes_by_identifier.get(original['pk'])
        if route is None:
            return JsonResponse({'error': f"Conflict: route '{original['pk']}' no longer exists."}, status=409)
        if (
            route.routestring != original['routestring']
            or route.group != original['group']
            or route.facilities != original['facilities']
            or route.tags != original['tags']
            or route.color != original['color']
        ):
            return JsonResponse({'error': f"Conflict: route '{original['pk']}' was changed by another user."}, status=409)

        route.delete()
        reserved_identifiers.discard(route.identifier)
        routes_by_identifier.pop(route.identifier, None)

    saved_routes = []
    for route_data in updates:
        current_identifier = route_data['pk']
        original = route_data['original']

        if current_identifier:
            route = routes_by_identifier.get(current_identifier)
            if route is None:
                return JsonResponse({'error': f"Conflict: route '{current_identifier}' no longer exists."}, status=409)
            if (
                route.routestring != original['routestring']
                or route.group != original['group']
                or route.facilities != original['facilities']
                or route.tags != original['tags']
                or route.color != original['color']
            ):
                return JsonResponse({'error': f"Conflict: route '{current_identifier}' was changed by another user."}, status=409)
        else:
            route = None

        new_identifier = route_data['identifier']
        taken = reserved_identifiers - ({current_identifier} if current_identifier else set())
        if new_identifier in taken:
            return JsonResponse({'error': f"Identifier '{new_identifier}' is already in use."}, status=400)

        if route is None:
            route = Route.objects.create(
                identifier=new_identifier,
                group=route_data['group'],
                routestring=route_data['routestring'],
                facilities=route_data['facilities'],
                tags=route_data['tags'],
                color=route_data['color'],
            )
        elif new_identifier == route.identifier:
            route.group = route_data['group']
            route.routestring = route_data['routestring']
            route.facilities = route_data['facilities']
            route.tags = route_data['tags']
            route.color = route_data['color']
            route.save(update_fields=['group', 'routestring', 'facilities', 'tags', 'color'])
        else:
            route.delete()
            reserved_identifiers.discard(current_identifier)
            routes_by_identifier.pop(current_identifier, None)
            route = Route.objects.create(
                identifier=new_identifier,
                group=route_data['group'],
                routestring=route_data['routestring'],
                facilities=route_data['facilities'],
                tags=route_data['tags'],
                color=route_data['color'],
            )

        reserved_identifiers.add(route.identifier)
        routes_by_identifier[route.identifier] = route
        saved_routes.append(_serialize_route(route))

    revision_number = _create_revision_snapshot(_sorted_routes_queryset())

    if saved_routes:
        notify_routes_changed(f"saved {len(saved_routes)} route(s)")
    return JsonResponse({'success': True, 'saved_routes': saved_routes, 'revision_number': revision_number})