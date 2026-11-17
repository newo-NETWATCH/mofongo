"""boto3 clients and tables, created once per Lambda environment and reused.

Every client is created with region_name from the settings (us-east-2). Timeouts and retries
are bounded so one slow call cannot eat the whole invocation.
"""

from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.config import Config

from settings import get_settings

_BASE = Config(
    retries={"mode": "standard", "total_max_attempts": 3},
    connect_timeout=3,
    read_timeout=5,
)


@lru_cache(maxsize=1)
def dynamodb_resource():
    return boto3.resource("dynamodb", region_name=get_settings().region, config=_BASE)


@lru_cache(maxsize=1)
def sns_client():
    return boto3.client("sns", region_name=get_settings().region, config=_BASE)


def items_table():
    return dynamodb_resource().Table(get_settings().items_table)


def reports_table():
    return dynamodb_resource().Table(get_settings().reports_table)


def matches_table():
    return dynamodb_resource().Table(get_settings().matches_table)
