import csv
import json
import logging

from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render

from routeplanner import api_client
from routeplanner.models import Location, Airway, AirwayWaypoint, Route, RouteRevisionSet, RouteRevisionEntry, CustomFix, HighlightedWaypoint
from routeplanner.permissions import is_administrator
from routeplanner.views.routeplotter import build_plotting_caches, normalize_route_text

logger = logging.getLogger(__name__)

@is_administrator
def waypoint_settings(request):
    waypoints_qs = Location.objects.all().order_by('identifier', 'id')
    paginator = Paginator(waypoints_qs, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'waypointsettings.html', {
        'page_obj': page_obj,
        'waypoints': page_obj.object_list,
        'total_waypoints': paginator.count,
    })

@is_administrator
def import_waypoints(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        waypoint_file = request.FILES['csv_file']
        decoded_file = waypoint_file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(decoded_file)
        
        waypoints_to_create = []
        
        for row in reader:
            waypoints_to_create.append(
                Location(
                    identifier=row['ident'],
                    longitude=float(row['lonx']),
                    latitude=float(row['laty']), 
                    waypoint_id=int(float(row['waypoint_id'])) if row.get('waypoint_id') else None
                )
            )
            
            if len(waypoints_to_create) >= 1000:
                Location.objects.bulk_create(waypoints_to_create, ignore_conflicts=True)
                waypoints_to_create = []

        if waypoints_to_create:
            Location.objects.bulk_create(waypoints_to_create, ignore_conflicts=True)

    return redirect('waypoint_settings')
@is_administrator
def delete_all_waypoints(request):
    if request.method == 'POST':
        Location.objects.all().delete()
    return redirect('waypoint_settings')


@is_administrator
def geojson_overlay_settings(request):
    overlays = api_client.list_geojson_overlays()
    return render(request, 'geojsonoverlayssettings.html', {'overlays': overlays})


def geojson_overlays_list(request):
    try:
        overlays = api_client.list_geojson_overlays()
    except Exception:
        return JsonResponse({'overlays': []})
    return JsonResponse({'overlays': [{'id': o.id, 'name': o.name, 'url': o.url} for o in overlays]})


@is_administrator
def geojson_overlay_add(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        url = request.POST.get('url', '').strip()
        if name and url:
            try:
                api_client.upsert_geojson_overlay(name, url)
            except Exception:
                pass
    return redirect('geojson_overlay_settings')


@is_administrator
def geojson_overlay_delete(request):
    if request.method == 'POST':
        overlay_id = request.POST.get('id')
        if overlay_id:
            try:
                api_client.delete_geojson_overlay(int(overlay_id))
            except Exception:
                pass
    return redirect('geojson_overlay_settings')


@is_administrator
def airway_settings(request):
    airway_count = Airway.objects.count()
    return render(request, "airwaysettings.html", {"airway_count": airway_count})

@is_administrator
def import_airway_segments(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        decoded_file = csv_file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(decoded_file)

        loc_cache = {loc.waypoint_id: loc for loc in Location.objects.filter(waypoint_id__isnull=False)}

        try:
            with transaction.atomic():
                rows_list = list(reader)

                # Collect waypoints missing from the DB in one pass.
                missing_waypoints = {}
                for row in rows_list:
                    from_id = int(row['from_waypoint_id'])
                    to_id = int(row['to_waypoint_id'])
                    if from_id not in loc_cache and from_id not in missing_waypoints:
                        missing_waypoints[from_id] = (row['from_lon'], row['from_lat'])
                    if to_id not in loc_cache and to_id not in missing_waypoints:
                        missing_waypoints[to_id] = (row['to_lon'], row['to_lat'])

                # Batch-create missing waypoints in one query.
                created_waypoints = {}
                if missing_waypoints:
                    created = Location.objects.bulk_create([
                        Location(waypoint_id=wp_id, longitude=float(lon), latitude=float(lat))
                        for wp_id, (lon, lat) in missing_waypoints.items()
                    ], ignore_conflicts=True)
                    for loc in created:
                        created_waypoints[loc.waypoint_id] = loc

                # Pre-create all airways in two queries (fetch existing, bulk-create new).
                airway_names = {row['airway_name'] for row in rows_list}
                airway_cache = {a.identifier: a for a in Airway.objects.filter(identifier__in=airway_names)}
                new_airways = [Airway(identifier=name) for name in airway_names if name not in airway_cache]
                if new_airways:
                    Airway.objects.bulk_create(new_airways, ignore_conflicts=True)
                    airway_cache = {a.identifier: a for a in Airway.objects.filter(identifier__in=airway_names)}

                # Build all AirwayWaypoint records in memory, then upsert in one batch.
                last_points = {}
                waypoint_map: dict[tuple, AirwayWaypoint] = {}
                for row in rows_list:
                    aw_name = row['airway_name']
                    seq = int(row['sequence_no'])
                    from_id = int(row['from_waypoint_id'])
                    to_id = int(row['to_waypoint_id'])

                    airway = airway_cache.get(aw_name)
                    start_node = loc_cache.get(from_id) or created_waypoints.get(from_id)
                    if airway and start_node:
                        # Use dict to deduplicate — last row wins for same (airway, order).
                        waypoint_map[(aw_name, seq)] = AirwayWaypoint(
                            airway=airway, waypoint=start_node, order=seq
                        )
                    last_points[aw_name] = {'waypoint_id': to_id, 'final_order': seq + 1}

                for aw_name, data in last_points.items():
                    airway = airway_cache.get(aw_name)
                    end_node = loc_cache.get(data['waypoint_id']) or created_waypoints.get(data['waypoint_id'])
                    if airway and end_node:
                        order = data['final_order']
                        waypoint_map[(aw_name, order)] = AirwayWaypoint(
                            airway=airway, waypoint=end_node, order=order
                        )

                if waypoint_map:
                    AirwayWaypoint.objects.bulk_create(
                        waypoint_map.values(),
                        update_conflicts=True,
                        update_fields=['waypoint'],
                        unique_fields=['airway', 'order'],
                    )

        except Exception as e:
            logger.exception("Airway import failed: %s", e)

    return redirect('airways_settings')

@is_administrator
def delete_all_airways(request):
    if request.method == 'POST':
        Airway.objects.all().delete()
    return redirect('airways_settings')


@is_administrator
def migration_settings(request):
    route_count = Route.objects.count()
    custom_fix_count = CustomFix.objects.count()
    highlighted_wp_count = HighlightedWaypoint.objects.count()
    revision_count = RouteRevisionSet.objects.count()

    target_event = None
    api_error = None
    try:
        events = api_client.get_events()
        if events:
            events_sorted = sorted(events, key=lambda e: e.get('date', ''), reverse=True)
            target_event = events_sorted[0]
    except Exception:
        api_error = "Could not reach ctp-api to determine target event."

    return render(request, 'migration.html', {
        'route_count': route_count,
        'custom_fix_count': custom_fix_count,
        'highlighted_wp_count': highlighted_wp_count,
        'revision_count': revision_count,
        'target_event': target_event,
        'api_error': api_error,
    })


@is_administrator
def run_migration(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    results = {
        'routes': 0,
        'custom_fixes': 0,
        'highlighted_waypoints': 0,
        'revisions': 0,
        'errors': [],
    }

    try:
        event = api_client.get_or_create_event()
        event_id = event.get('id')
    except Exception as e:
        logger.exception("Migration: failed to get or create event")
        return JsonResponse({'errors': [f"Event: {e}"]})

    local_routes = list(Route.objects.order_by('group', 'identifier'))
    if local_routes:
        all_normalized = [normalize_route_text(r.routestring) for r in local_routes]
        try:
            caches = build_plotting_caches(all_normalized)
        except Exception:
            logger.exception("Migration: failed to build plotting caches")
            caches = {}

        segments = []
        for route in local_routes:
            tags = [{'tag': t} for t in route.tags.split() if t] if route.tags else []
            normalized = normalize_route_text(route.routestring)
            try:
                locations = api_client.resolve_route_to_locations(normalized, caches)
            except Exception:
                logger.exception("Migration: failed to resolve locations for route %s", route.identifier)
                locations = []
            segments.append({
                'identifier': route.identifier,
                'routeSegmentGroup': route.group,
                'routeString': route.routestring,
                'facilities': route.facilities,
                'color': route.color,
                'enabled': route.enabled,
                'tags': tags,
                'locations': locations,
                'eventId': event_id,
            })
        try:
            api_client.batch_save_routes(event_id, updates=segments, deletes=[])
            results['routes'] = len(segments)
        except Exception as e:
            logger.exception("Migration: failed to migrate routes")
            results['errors'].append(f"Routes: {e}")

    local_fixes = list(CustomFix.objects.all())
    for fix in local_fixes:
        try:
            api_client.upsert_custom_fix(fix.identifier, fix.latitude, fix.longitude, fix.note)
            results['custom_fixes'] += 1
        except Exception as e:
            logger.exception("Migration: failed to migrate custom fix %s", fix.identifier)
            results['errors'].append(f"Custom fix {fix.identifier}: {e}")

    local_highlighted = list(HighlightedWaypoint.objects.all())
    for hw in local_highlighted:
        try:
            api_client.upsert_highlighted_waypoint(hw.identifier, hw.color, hw.note)
            results['highlighted_waypoints'] += 1
        except Exception as e:
            logger.exception("Migration: failed to migrate highlighted waypoint %s", hw.identifier)
            results['errors'].append(f"Highlighted waypoint {hw.identifier}: {e}")

    if results['routes'] > 0:
        try:
            api_client.create_route_revision(event_id)
            results['revisions'] = 1
        except Exception as e:
            logger.exception("Migration: failed to create route revision")
            results['errors'].append(f"Route revision: {e}")

    return JsonResponse(results)