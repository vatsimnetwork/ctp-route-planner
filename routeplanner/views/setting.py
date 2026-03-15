from django.views import View
from django.shortcuts import redirect, render
from django.core.paginator import Paginator
from routeplanner.models import Location
import csv

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

def import_waypoints(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        waypoint_file = request.FILES['csv_file']
        decoded_file = waypoint_file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(decoded_file)
        for row in reader:
            print(row)
            Location.objects.create(
                identifier=row['ident'],
                longitude=float(row['lonx']),
                latitude=float(row['laty'])
            )

    return redirect('waypoint_settings')

def delete_all_waypoints(request):
    if request.method == 'POST':
        Location.objects.all().delete()
    return redirect('waypoint_settings')