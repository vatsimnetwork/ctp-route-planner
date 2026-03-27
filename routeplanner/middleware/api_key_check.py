import requests
from django.conf import settings
from django.http import JsonResponse


class ApiKeyCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return JsonResponse({'error': 'unauthorized', 'message': 'missing api key'}, status=401)

        try:
            response = requests.get(
                f"{settings.AUTH_INTERNAL_URL}/internal/apikey/validate",
                headers={'X-API-Key': api_key},
                timeout=2,
            )
        except requests.RequestException:
            return JsonResponse({'error': 'internal_error', 'message': 'could not reach auth service'}, status=503)

        if response.status_code == 200:
            return self.get_response(request)

        try:
            body = response.json()
        except ValueError:
            body = {'error': 'internal_error', 'message': 'unexpected response from auth service'}

        return JsonResponse(body, status=response.status_code)
