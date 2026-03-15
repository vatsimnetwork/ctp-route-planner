import json

from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.http import JsonResponse
from django.shortcuts import render

from routeplanner.discord import notify_routes_changed
from routeplanner.models import (
    ROUTE_TYPE_CHOICES,
    Route,
    build_unique_route_identifier,
    normalize_route_type,
)


TYPE_SORT_ORDER = {
    'AMAS': 0,
    'EMEA': 1,
    'NAT': 2,
}


def _sorted_routes_queryset():
    type_order = Case(
        *[When(type=route_type, then=Value(order)) for route_type, order in TYPE_SORT_ORDER.items()],
        default=Value(999),
        output_field=IntegerField(),
    )
    return Route.objects.annotate(type_order=type_order).order_by('type_order', 'identifier')


def _serialize_route(route):
    return {
        'pk': route.identifier,
        'identifier': route.identifier,
        'routestring': route.routestring,
        'type': normalize_route_type(route.type),
    }


def _validate_route_payload(route_data, require_original=False, require_current_values=True):
    routestring = (route_data.get('routestring') or '').strip()
    route_type = normalize_route_type(route_data.get('type'))
    original = route_data.get('original') or {}

    if require_current_values and not routestring:
        return None, 'Route string is required.'
    if require_current_values and (',' in routestring or ';' in routestring):
        return None, 'Commas and semicolons are not allowed in route strings.'
    if require_current_values and route_type not in {choice[0] for choice in ROUTE_TYPE_CHOICES}:
        return None, f"Invalid route type: {route_data.get('type')}"

    validated = {
        'pk': (route_data.get('pk') or '').strip(),
        'identifier': (route_data.get('identifier') or '').strip().upper(),
        'routestring': routestring,
        'type': route_type,
        'original': {
            'pk': (original.get('pk') or '').strip(),
            'routestring': (original.get('routestring') or '').strip(),
            'type': normalize_route_type(original.get('type')),
        },
    }

    if require_original and not validated['original']['pk']:
        return None, 'Original route reference is missing.'

    return validated, None


def routes(request):
    route_list = _sorted_routes_queryset()
    choices = list(ROUTE_TYPE_CHOICES)
    return render(request, 'routes.html', {
        'routes': route_list,
        'route_type_choices': choices,
        'route_type_choices_json': json.dumps(choices),
    })


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
    original_type = normalize_route_type(original.get('type'))

    if not original_pk or original_pk != identifier:
        return JsonResponse({'error': 'Original route reference is missing.'}, status=400)

    try:
        route = Route.objects.select_for_update().get(identifier=identifier)
    except Route.DoesNotExist:
        # Already gone — treat as success
        return JsonResponse({'success': True})

    route.delete()
    notify_routes_changed(f"deleted '{identifier}'")
    return JsonResponse({'success': True})


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
        if route.routestring != original['routestring'] or normalize_route_type(route.type) != original['type']:
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
            if route.routestring != original['routestring'] or normalize_route_type(route.type) != original['type']:
                return JsonResponse({'error': f"Conflict: route '{current_identifier}' was changed by another user."}, status=409)
        else:
            route = None

        if route_data['type'] == 'NAT':
            new_identifier = route_data['identifier']
            if not new_identifier:
                return JsonResponse({'error': 'NAT routes require a custom identifier.'}, status=400)
            if ' ' in new_identifier or ',' in new_identifier or ';' in new_identifier:
                return JsonResponse({'error': 'NAT identifier cannot contain spaces, commas, or semicolons.'}, status=400)
            taken = reserved_identifiers - ({current_identifier} if current_identifier else set())
            if new_identifier in taken:
                return JsonResponse({'error': f"Identifier '{new_identifier}' is already in use."}, status=400)
        else:
            new_identifier = build_unique_route_identifier(
                route_data['routestring'],
                reserved_identifiers,
                current_identifier=current_identifier,
            )
            if not new_identifier:
                return JsonResponse({'error': 'Route string must contain at least one waypoint.'}, status=400)

        if route is None:
            route = Route.objects.create(
                identifier=new_identifier,
                routestring=route_data['routestring'],
                type=route_data['type'],
            )
        elif new_identifier == route.identifier:
            route.routestring = route_data['routestring']
            route.type = route_data['type']
            route.save(update_fields=['routestring', 'type'])
        else:
            route.delete()
            reserved_identifiers.discard(current_identifier)
            routes_by_identifier.pop(current_identifier, None)
            route = Route.objects.create(
                identifier=new_identifier,
                routestring=route_data['routestring'],
                type=route_data['type'],
            )

        reserved_identifiers.add(route.identifier)
        routes_by_identifier[route.identifier] = route
        saved_routes.append(_serialize_route(route))

    if saved_routes:
        notify_routes_changed(f"saved {len(saved_routes)} route(s)")
    return JsonResponse({'success': True, 'saved_routes': saved_routes})