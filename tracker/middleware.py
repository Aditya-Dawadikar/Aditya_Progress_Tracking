import logging
import time
import uuid

from django.conf import settings
from django.http import HttpResponsePermanentRedirect

HEALTHCHECK_HOST = "healthcheck.railway.app"
logger = logging.getLogger(__name__)


class RequestTraceMiddleware:
    """Emit one safe, correlated trace line for every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = uuid.uuid4().hex[:12]
        started_at = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception:
            logger.exception(
                "request_trace request_id=%s method=%s path=%s status=500 duration_ms=%d",
                request_id,
                request.method,
                request.path,
                (time.perf_counter() - started_at) * 1000,
            )
            raise

        response["X-Request-ID"] = request_id
        logger.info(
            "request_trace request_id=%s method=%s path=%s status=%s duration_ms=%d",
            request_id,
            request.method,
            request.path,
            response.status_code,
            (time.perf_counter() - started_at) * 1000,
        )
        return response


class CurrentMemberMiddleware:
    """Resolves the session's chosen Member (see /whoami/) onto request.member.

    This is the app's whole "auth" model: no passwords, just a name picked
    from a shared session-backed identity. request.member is None until one
    is chosen.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from tracker.models import Member

        request.member = None
        request.members = Member.objects.all()
        member_id = request.session.get("member_id")
        if member_id:
            request.member = Member.objects.filter(pk=member_id).first()
            if request.member is None:
                del request.session["member_id"]
        return self.get_response(request)


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
