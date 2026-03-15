from django.urls import path
from django.conf import settings
from django.views.generic import RedirectView

from .views.home import home
from .views.routeplotter import index, fir_geojson, waypoints_geojson
from.views.setting import waypoint_settings, import_waypoints, delete_all_waypoints
from .views.routes import route_delete, routes, routes_save


urlpatterns = [
    path('', home, name='home'),
    path(
        'auth/logout/',
        RedirectView.as_view(
            url=f'{getattr(settings, "AUTH_SERVICE_URL", "http://auth-panel:8000")}/auth/logout/',
            permanent=False,
        ),
        name='logout',
    ),
    path(
        'auth/login/',
        RedirectView.as_view(
            url=f'{getattr(settings, "AUTH_SERVICE_URL", "http://auth-panel:8000")}/auth/login/',
            permanent=False,
        ),
        name='login',
    ),
    path('routeplotter/', index, name='routeplotter'),
    path('routeplotter/getfirs/', fir_geojson, name='fir_geojson'),
    path('routeplotter/getwaypoints/', waypoints_geojson, name='waypoints_geojson'),
    path('settings/waypoints/', waypoint_settings, name='waypoint_settings'),
    path('settings/waypoints/import/', import_waypoints, name='import_waypoints'),
    path('settings/waypoints/deleteall/', delete_all_waypoints, name='delete_all_waypoints'),
    path('routes/', routes, name='routes'),
    path('routes/save/', routes_save, name='routes_save'),
    path('routes/delete/<str:identifier>/', route_delete, name='route_delete'),
]