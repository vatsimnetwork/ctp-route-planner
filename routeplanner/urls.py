from django.urls import path
from django.conf import settings
from django.views.generic import RedirectView

from .views.home import home
from .views.routeplotter import index, fir_geojson


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
]