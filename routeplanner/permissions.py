from functools import wraps
from django.http import JsonResponse

WRITE_ROLES = {'route_staff', 'developer', 'administrator'}


def write_access_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not WRITE_ROLES.intersection(request.user_roles):
            return JsonResponse({'error': 'Forbidden'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper

def is_administrator(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if 'administrator' not in request.user_roles or request.user_cid != "1745968":
            return JsonResponse({'error': 'Forbidden'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper
