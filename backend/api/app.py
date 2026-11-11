"""Lambda entry point for the Mofongo REST API (API Gateway payload format 1.0).

One function answers all 10 routes. API Gateway has already checked the Cognito token and
validated the create-item and create-report bodies. This code checks again (defense in
depth) and does the rest: token_use, body size, path and query values, ownership.

Event fields used (format 1.0, REST proxy):
  httpMethod, resource (the route template), pathParameters, queryStringParameters,
  multiValueQueryStringParameters, headers (case-sensitive), body, isBase64Encoded,
  requestContext.authorizer.claims.
"""

from __future__ import annotations

import logging
import os

import alerts
import items
import reports
from auth import authenticate
from errors import ApiError
from responses import json_response

logging.getLogger().setLevel(getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO))
logger = logging.getLogger(__name__)

# (method, API Gateway resource path) -> function. Mirrors the 10 operations in api/openapi.yaml.
ROUTES = {
    ("GET", "/items"): items.list_items,  # listItems
    ("POST", "/items"): items.create_item,  # createItem
    ("GET", "/items/{itemId}"): items.get_item,  # getItem
    ("POST", "/items/{itemId}/returned"): items.mark_item_returned,  # markItemReturned
    ("GET", "/reports"): reports.list_reports,  # listReports
    ("POST", "/reports"): reports.create_report,  # createReport
    ("GET", "/reports/{reportId}"): reports.get_report,  # getReport
    ("POST", "/reports/{reportId}/closed"): reports.close_report,  # closeReport
    ("GET", "/me/alerts"): alerts.get_my_alerts,  # getMyAlerts
    ("POST", "/me/alerts"): alerts.subscribe_my_alerts,  # subscribeMyAlerts
}


def handler(event, context=None):
    method = str(event.get("httpMethod", "")).upper()
    resource = str(event.get("resource", ""))
    try:
        caller = authenticate(event)  # 401 first, on every route
        route = ROUTES.get((method, resource))
        if route is None:
            raise ApiError(404, "Not found.")
        status, body = route(event, caller)
    except ApiError as error:
        status, body = error.status, error.body()
    except Exception:
        # Details go to the log. The client gets a fixed message (api/openapi.yaml ServerError).
        logger.exception("Unhandled error on %s %s", method, resource)
        status, body = 500, {"message": "Something went wrong. Try again later."}

    # Method, route template and status only. Never log the token, claims, email or body.
    logger.info("%s %s -> %s", method, resource, status)
    return json_response(status, body)
