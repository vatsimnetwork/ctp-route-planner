import requests
from django.http import HttpResponseRedirect
from django.conf import settings
from django.urls import resolve


class SessionCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session_key = request.COOKIES.get('session_id')

        #request.is_session_valid = False
        #request.user_cid = None
        #request.user_roles = []

        request.is_session_valid = True
        request.user_cid = 84531
        request.user_roles = ["routeplanner_route_acces", "routeplanner_routeplotter_acces", "routeplanner_setting_acces"]

        #if session_key:
        #    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        #    client_ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR', '')
        #    try:
        #        auth_url = getattr(settings, 'AUTH_SERVICE_URL', 'http://auth-panel:8000')
        #        internal_api_key = getattr(settings, 'INTERNAL_API_KEY', '')
        #        response = requests.get(
        #            f"{auth_url}/internal/session/validate",
        #            headers={
        #                "X-Internal-Key": internal_api_key,
        #                "Cookie": f"session_id={session_key}",
        #                "User-Agent": request.headers.get("user-agent", ""),
        #                "X-Forwarded-For": client_ip,
        #            },
        #            timeout=2,
        #        )
        #        if response.status_code == 200:
        #            data = response.json()
        #            request.is_session_valid = True
        #            request.user_cid = data.get('cid')
        #            request.user_roles = data.get('roles', [])
        #    except requests.RequestException:
        #        pass

        view_func, _, _ = resolve(request.path)

        is_exempt = getattr(view_func, 'login_not_required', False) or \
                    request.path.startswith('/admin/') or \
                    request.path == '/login/'

        #if not request.is_session_valid and not is_exempt:
        #    auth_url = getattr(settings, 'AUTH_SERVICE_URL', 'http://auth-panel:8000')
        #    return HttpResponseRedirect(f'{auth_url}/auth/login/')

        return self.get_response(request)