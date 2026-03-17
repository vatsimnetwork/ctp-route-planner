"""
Just some scuffed genrated stuff to secure in case of data incosistency
"""

import csv
import io
import logging
import threading
from datetime import datetime, timezone

import requests
from django.conf import settings

from routeplanner.models import Route

logger = logging.getLogger(__name__)


def _build_csv() -> bytes:
    routes = Route.objects.all().order_by("group", "identifier")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["identifier", "group", "routestring", "facilities", "tags"])
    for route in routes:
        writer.writerow([
            route.identifier,
            route.group,
            route.routestring,
            route.facilities,
            route.tags,
        ])
    return buf.getvalue().encode("utf-8")


def _send(action: str) -> None:
    webhook_url = getattr(settings, "DISCORD_ROUTES_WEBHOOK_URL", "")
    if not webhook_url:
        return

    try:
        csv_bytes = _build_csv()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"routes_{timestamp}.csv"

        response = requests.post(
            webhook_url,
            data={"content": f"Routes updated — **{action}** (`{timestamp} UTC`)"},
            files={"file": (filename, csv_bytes, "text/csv")},
            timeout=10,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Discord webhook failed: %s", exc)


def notify_routes_changed(action: str) -> None:
    """Fire-and-forget: sends the CSV in a background thread."""
    threading.Thread(target=_send, args=(action,), daemon=True).start()
