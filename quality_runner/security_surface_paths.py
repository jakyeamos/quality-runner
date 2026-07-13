from __future__ import annotations

API_ROUTE_MARKERS = (
    "app/api/",
    "pages/api/",
    "src/routes/",
    "routes/api/",
    "api/",
)
WEBHOOK_MARKERS = ("webhook", "webhooks")


def is_api_route_path(relative_path: str) -> bool:
    return any(marker in relative_path for marker in API_ROUTE_MARKERS)


def is_webhook_path(relative_path: str) -> bool:
    return any(marker in relative_path.lower() for marker in WEBHOOK_MARKERS)


def is_security_surface_path(relative_path: str) -> bool:
    return is_api_route_path(relative_path) or is_webhook_path(relative_path)
