from django.conf import settings
from django.urls import include, path

_prefix = f'{settings.MOUNT_PATH}/' if settings.MOUNT_PATH else ''

urlpatterns = [
    path(_prefix, include('routeplanner.urls')),
]