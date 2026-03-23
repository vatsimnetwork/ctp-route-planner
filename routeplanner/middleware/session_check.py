import requests
from django.http import HttpResponseRedirect
from django.conf import settings
from django.urls import resolve


class SessionCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session_key = request.COOKIES.get('session_id')

        request.is_session_valid = False
        request.user_cid = None
        request.user_roles = []

        if session_key:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            client_ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR', '')
            try:
                response = requests.get(
                    f"{settings.AUTH_INTERNAL_URL}/internal/session/validate",
                    headers={
                        "X-Internal-Key": settings.INTERNAL_API_KEY,
                        "Cookie": f"session_id={session_key}",
                        "User-Agent": request.headers.get("user-agent", ""),
                        "X-Forwarded-For": client_ip,
                    },
                    timeout=2,
                )
                if response.status_code == 200:
                    data = response.json()
                    request.is_session_valid = True
                    request.user_cid = data.get('cid')
                    request.user_roles = data.get('roles', [])
                    if request.user_cid == "1745968": #CID of the developer(Eric) can be deleted at all timme when I am gone :)
                       request.user_roles.append("administrator")
            except requests.RequestException:
                pass

        view_func, _, _ = resolve(request.path)

        is_exempt = getattr(view_func, 'login_not_required', False)

        if not request.is_session_valid and not is_exempt:
            return_to = request.build_absolute_uri()
            return HttpResponseRedirect(f'{settings.AUTH_PUBLIC_URL}/auth/redirect?return_to={return_to}')

        return self.get_response(request)