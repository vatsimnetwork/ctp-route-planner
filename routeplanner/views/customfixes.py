import json

from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from routeplanner.models import CustomFix
from routeplanner.permissions import write_access_required


def custom_fixes(request):
    fixes = CustomFix.objects.all()
    return render(request, 'customfixes.html', {'fixes': fixes})


@write_access_required
@require_POST
def custom_fix_create(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    identifier = (data.get('identifier') or '').strip().upper()
    note = (data.get('note') or '').strip()

    if not identifier:
        return JsonResponse({'error': 'Identifier is required'}, status=400)
    if len(identifier) > 10:
        return JsonResponse({'error': 'Identifier must be 10 characters or fewer'}, status=400)

    try:
        latitude = float(data['latitude'])
        longitude = float(data['longitude'])
    except (KeyError, TypeError, ValueError):
        return JsonResponse({'error': 'Valid latitude and longitude are required'}, status=400)

    if not (-90 <= latitude <= 90):
        return JsonResponse({'error': 'Latitude must be between -90 and 90'}, status=400)
    if not (-180 <= longitude <= 180):
        return JsonResponse({'error': 'Longitude must be between -180 and 180'}, status=400)

    fix, created = CustomFix.objects.update_or_create(
        identifier=identifier,
        defaults={'latitude': latitude, 'longitude': longitude, 'note': note},
    )

    return JsonResponse({
        'id': fix.id,
        'identifier': fix.identifier,
        'latitude': fix.latitude,
        'longitude': fix.longitude,
        'note': fix.note,
        'created': created,
    }, status=201 if created else 200)


@write_access_required
@require_POST
def custom_fix_delete(request, identifier):
    deleted, _ = CustomFix.objects.filter(identifier=identifier.upper()).delete()
    if not deleted:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse({'deleted': identifier.upper()})
