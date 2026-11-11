"""boto3 clients and tables, created once per Lambda environment and reused.

Every client is created with region_name from the settings (us-east-2). Timeouts and
retries are set so a slow AWS call cannot outlive the API Gateway integration timeout.
"""

from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.config import Config

from config import get_settings

_BASE = Config(
    retries={"mode": "standard", "total_max_attempts": 3},
    connect_timeout=3,
    read_timeout=4,
)

# Presigned URLs must be signed with SigV4 against the regional, virtual-hosted endpoint,
# or S3 in us-east-2 answers with a redirect or a signature error.
_S3 = Config(
    signature_version="s3v4",
    s3={"addressing_style": "virtual"},
    retries={"mode": "standard", "total_max_attempts": 3},
    connect_timeout=3,
    read_timeout=4,
)


@lru_cache(maxsize=1)
def dynamodb_resource():
    return boto3.resource("dynamodb", region_name=get_settings().region, config=_BASE)


@lru_cache(maxsize=1)
def s3_client():
    return boto3.client("s3", region_name=get_settings().region, config=_S3)


@lru_cache(maxsize=1)
def sns_client():
    return boto3.client("sns", region_name=get_settings().region, config=_BASE)


def items_table():
    return dynamodb_resource().Table(get_settings().items_table)


def reports_table():
    return dynamodb_resource().Table(get_settings().reports_table)


def matches_table():
    return dynamodb_resource().Table(get_settings().matches_table)


def users_table():
    return dynamodb_resource().Table(get_settings().users_table)
