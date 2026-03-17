from django.urls import path
from django.conf import settings
from django.http import HttpResponseRedirect
from django.views.generic import RedirectView

from .views.home import home
from .views.routeplotter import index, fir_geojson, waypoints_geojson, plot_route
from .views.setting import waypoint_settings, import_waypoints, delete_all_waypoints, firboundaries_settings, upload_fir_boundaries, delete_fir_boundaries, airway_settings, import_airway_segments, delete_all_airways
from .views.routes import route_delete, routes, routes_save


urlpatterns = [
    path('', home, name='home'),
    path(
        'auth/logout/',
        RedirectView.as_view(url=f'{settings.AUTH_PUBLIC_URL}/auth/logout/', permanent=False),
        name='logout',
    ),
    path(
        'auth/login/',
        lambda request: HttpResponseRedirect(f'{settings.AUTH_PUBLIC_URL}/auth/redirect?return_to={settings.APP_URL}'),
        name='login',
    ),
    path('routeplotter/', index, name='routeplotter'),
    path('routeplotter/getfirs/', fir_geojson, name='fir_geojson'),
    path('routeplotter/getwaypoints/', waypoints_geojson, name='waypoints_geojson'),
    path('routeplotter/plotroute/', plot_route, name='plot_route'),
    path('settings/waypoints/', waypoint_settings, name='waypoint_settings'),
    path('settings/waypoints/import/', import_waypoints, name='import_waypoints'),
    path('settings/waypoints/deleteall/', delete_all_waypoints, name='delete_all_waypoints'),
    path('settings/firboundaries/', firboundaries_settings, name='firboundaries_settings'),
    path('settings/firboundaries/upload/', upload_fir_boundaries, name='upload_fir_boundaries'),
    path('settings/firboundaries/delete/', delete_fir_boundaries, name='delete_fir_boundaries'),
    path('routes/', routes, name='routes'),
    path('routes/save/', routes_save, name='routes_save'),
    path('routes/delete/<str:identifier>/', route_delete, name='route_delete'),
    path('settings/airways/', airway_settings, name='airways_settings'),
    path('settings/airways/import/', import_airway_segments, name='import_airways'),
    path('settings/airways/deleteall/', delete_all_airways, name='delete_all_airways'),
]