from django.conf import settings
from django.http import HttpResponsePermanentRedirect

HEALTHCHECK_HOST = "healthcheck.railway.app"


class HealthcheckSafeSSLRedirectMiddleware:
    """Equivalent to SecurityMiddleware's SECURE_SSL_REDIRECT, except it
    never redirects Railway's internal healthcheck prober.

    That prober connects to the container over plain HTTP before the
    deployment is live (there's no edge TLS terminator in front of it yet)
    and does not follow redirects, so a blanket SECURE_SSL_REDIRECT turns
    every healthcheck's 200 into a 301 and the deploy never goes healthy.
    Real end-user traffic still gets redirected to HTTPS.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = not settings.DEBUG

    def __call__(self, request):
        if (
            self.enabled
            and not request.is_secure()
            and request.get_host().split(":")[0] != HEALTHCHECK_HOST
        ):
            url = request.build_absolute_uri(request.get_full_path())
            url = url.replace("http://", "https://", 1)
            return HttpResponsePermanentRedirect(url)
        return self.get_response(request)
