from django.views import View
from django.shortcuts import redirect, render
from django.core.paginator import Paginator
from django.conf import settings
from routeplanner.models import Location, Airway, AirwayWaypoint
from routeplanner.permissions import is_administrator
from django.db import transaction
import csv
import json

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
    return render(request, "airwaysettings.html")

@is_administrator
def import_airway_segments(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        
        decoded_file = csv_file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(decoded_file)

        loc_cache = {l.waypoint_id: l for l in Location.objects.filter(waypoint_id__isnull=False)}
        
        last_points = {}

        try:
            with transaction.atomic():


                for row in reader:
                    aw_name = row['airway_name']
                    seq = int(row['sequence_no'])
                    from_id = int(row['from_waypoint_id'])
                    to_id = int(row['to_waypoint_id'])

                    airway, _ = Airway.objects.get_or_create(identifier=aw_name)

                    start_node = loc_cache.get(from_id)

                    if start_node:
                        AirwayWaypoint.objects.update_or_create(
                            airway=airway,
                            order=seq,
                            defaults={'waypoint': start_node}
                        )

                    last_points[aw_name] = {
                        'waypoint_id': to_id,
                        'final_order': seq + 1
                    }

                for aw_name, data in last_points.items():
                    end_node = loc_cache.get(data['waypoint_id'])
                    if end_node:
                        airway = Airway.objects.get(identifier=aw_name)
                        AirwayWaypoint.objects.update_or_create(
                            airway=airway,
                            order=data['final_order'],
                            defaults={'waypoint': end_node}
                        )

        except Exception as e:
            print(e)

            
    return redirect('airways_settings')

@is_administrator
def delete_all_airways(request):
    if request.method == 'POST':
        Airway.objects.all().delete()
    return redirect('airways_settings')