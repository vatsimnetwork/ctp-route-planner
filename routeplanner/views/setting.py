import csv
import json
import logging

from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import redirect, render

from routeplanner.models import Location, Airway, AirwayWaypoint
from routeplanner.permissions import is_administrator

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
def firboundaries_settings(request):
    has_local = settings.FIR_BOUNDARIES_PATH.exists()
    return render(request, 'firboundariessettings.html', {'has_local': has_local})

@is_administrator
def upload_fir_boundaries(request):
    if request.method != 'POST':
        return redirect('firboundaries_settings')

    uploaded = request.FILES.get('geojson_file')
    if not uploaded:
        return redirect('firboundaries_settings')

    if not uploaded.name.lower().endswith(('.geojson', '.json')):
        return redirect('firboundaries_settings')

    raw = uploaded.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return redirect('firboundaries_settings')

    if data.get('type') != 'FeatureCollection':
        return redirect('firboundaries_settings')

    path = settings.FIR_BOUNDARIES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)

    return redirect('firboundaries_settings')

@is_administrator
def delete_fir_boundaries(request):
    if request.method == 'POST':
        path = settings.FIR_BOUNDARIES_PATH
        if path.exists():
            path.unlink()
    return redirect('firboundaries_settings')

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