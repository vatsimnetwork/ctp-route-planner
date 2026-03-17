from functools import wraps
from django.http import JsonResponse

WRITE_ROLES = {'route_staff', 'developers', 'administrators'}


def write_access_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not WRITE_ROLES.intersection(request.user_roles):
            return JsonResponse({'error': 'Forbidden'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper
