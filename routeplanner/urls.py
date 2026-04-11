from django.urls import path
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.views.decorators.http import require_POST

from .views.home import home
from .views.routeplotter import index, waypoints_geojson, plot_route, throughput_data
from .views.highlightedwaypoints import highlighted_waypoints, highlighted_waypoint_create, highlighted_waypoint_delete, highlighted_waypoints_geojson
from .views.setting import waypoint_settings, import_waypoints, delete_all_waypoints, geojson_overlay_settings, geojson_overlay_add, geojson_overlay_delete, geojson_overlays_list, airway_settings, import_airway_segments, delete_all_airways, migration_settings, run_migration
from .views.routes import route_delete, routes, routes_save
from .views.customfixes import custom_fixes, custom_fix_create, custom_fix_delete

@require_POST
def _logout(request):
    sso_logout_url = f'{settings.AUTH_PUBLIC_URL}/auth/logout/'
    return HttpResponse(
        f'<!DOCTYPE html><html><body>'
        f'<form id="f" method="post" action="{sso_logout_url}"></form>'
        f'<script>document.getElementById("f").submit();</script>'
        f'</body></html>'
    )


urlpatterns = [
    path('', home, name='home'),
    path('auth/logout/', _logout, name='logout'),
    path(
        'auth/login/',
        lambda request: HttpResponseRedirect(f'{settings.AUTH_PUBLIC_URL}/auth/redirect?return_to={settings.APP_URL}'),
        name='login',
    ),
    path('routeplotter/', index, name='routeplotter'),
    path('routeplotter/getwaypoints/', waypoints_geojson, name='waypoints_geojson'),
    path('routeplotter/plotroute/', plot_route, name='plot_route'),
    path('routeplotter/throughput/', throughput_data, name='throughput_data'),
    path('settings/waypoints/', waypoint_settings, name='waypoint_settings'),
    path('settings/waypoints/import/', import_waypoints, name='import_waypoints'),
    path('settings/waypoints/deleteall/', delete_all_waypoints, name='delete_all_waypoints'),
    path('settings/geojsonoverlays/', geojson_overlay_settings, name='geojson_overlay_settings'),
    path('settings/geojsonoverlays/add/', geojson_overlay_add, name='geojson_overlay_add'),
    path('settings/geojsonoverlays/delete/', geojson_overlay_delete, name='geojson_overlay_delete'),
    path('settings/geojsonoverlays/list/', geojson_overlays_list, name='geojson_overlays_list'),
    path('routes/', routes, name='routes'),
    path('routes/save/', routes_save, name='routes_save'),
    path('routes/delete/<str:identifier>/', route_delete, name='route_delete'),
    path('settings/airways/', airway_settings, name='airways_settings'),
    path('settings/airways/import/', import_airway_segments, name='import_airways'),
    path('settings/airways/deleteall/', delete_all_airways, name='delete_all_airways'),
    path('customfixes/', custom_fixes, name='custom_fixes'),
    path('customfixes/create/', custom_fix_create, name='custom_fix_create'),
    path('customfixes/delete/<str:identifier>/', custom_fix_delete, name='custom_fix_delete'),
    path('settings/highlightedwaypoints/', highlighted_waypoints, name='highlighted_waypoints'),
    path('settings/highlightedwaypoints/create/', highlighted_waypoint_create, name='highlighted_waypoint_create'),
    path('settings/highlightedwaypoints/delete/<str:identifier>/', highlighted_waypoint_delete, name='highlighted_waypoint_delete'),
    path('routeplotter/gethighlightedwaypoints/', highlighted_waypoints_geojson, name='highlighted_waypoints_geojson'),
    path('settings/migration/', migration_settings, name='migration_settings'),
    path('settings/migration/run/', run_migration, name='run_migration'),
]