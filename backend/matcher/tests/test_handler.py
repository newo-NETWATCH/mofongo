"""The stream handler end to end under moto: both directions, idempotency, SNS failure paths."""

from __future__ import annotations

import json

import pytest
from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError

from conftest import TEST_ENV, make_item, make_report, new_id, stream_record

ITEMS = TEST_ENV["ITEMS_TABLE"]
REPORTS = TEST_ENV["REPORTS_TABLE"]


def run(*records):
    import app

    return app.handler({"Records": list(records)}, None)


def tagged_event(item, seq="1"):
    old = {**item, "tagStatus": "PENDING"}
    old.pop("clipTags", None)
    return stream_record(ITEMS, "MODIFY", new=item, old=old, seq=seq)


def report_event(report, seq="1"):
    return stream_record(REPORTS, "INSERT", new=report, seq=seq)


def seed_item(aws, **kw):
    item = make_item(**kw)
    aws.items.put_item(Item=item)
    return item


def seed_report(aws, **kw):
    report = make_report(**kw)
    aws.reports.put_item(Item=report)
    return report


def match_rows(aws):
    return aws.matches.scan()["Items"]


# ---- direction A ----------------------------------------------------------------------------

def test_direction_a_records_and_notifies_the_owner_only(aws):
    owner, other_owner = new_id(), new_id()
    queue, other_queue = aws.subscribe_owner(owner), aws.subscribe_owner(other_owner)
    report = seed_report(aws, ownerId=owner, colors=["black"])
    seed_report(aws, ownerId=other_owner, colors=["red"])  # scores 52, no match
    item = seed_item(aws)

    assert run(tagged_event(item)) == {"batchItemFailures": []}

    rows = match_rows(aws)
    assert len(rows) == 1
    row = rows[0]
    assert (row["reportId"], row["itemId"]) == (report["reportId"], item["itemId"])
    assert row["score"] == 91 and row["scoreParts"]["clipColor"] == 9
    assert 2 <= len(row["why"]) <= 4
    assert row["createdAt"].endswith("Z") and row["notifiedAt"].endswith("Z")

    got = aws.messages(queue)
    assert len(got) == 1
    assert f"{TEST_ENV['SITE_URL'].rstrip('/')}/reports/{report['reportId']}" in got[0]["Body"]
    assert aws.messages(other_queue) == []


def test_direction_a_ignores_other_categories_and_closed_reports(aws):
    seed_report(aws, category="keys", colors=["black"])
    closed = make_report(colors=["black"], status="CLOSED")  # no openCategory -> not in the index
    aws.reports.put_item(Item=closed)
    run(tagged_event(seed_item(aws)))
    assert match_rows(aws) == []


def test_below_threshold_records_nothing(aws):
    seed_report(aws, colors=["red"])
    run(tagged_event(seed_item(aws)))
    assert match_rows(aws) == []


def test_threshold_is_read_from_the_environment(aws, monkeypatch):
    monkeypatch.setenv("MATCH_THRESHOLD", "50")
    import settings
    settings.get_settings.cache_clear()
    seed_report(aws, colors=["red"])  # scores 52
    run(tagged_event(seed_item(aws)))
    assert len(match_rows(aws)) == 1


def test_item_record_that_is_not_a_tagging_event_is_ignored(aws):
    seed_report(aws)
    item = make_item()
    insert = stream_record(ITEMS, "INSERT", new=item)
    returned = make_item(status="RETURNED")
    modify_returned = stream_record(ITEMS, "MODIFY", new=returned, old={**returned, "tagStatus": "PENDING"})
    already = stream_record(ITEMS, "MODIFY", new=item, old=item)  # TAGGED -> TAGGED
    remove = stream_record(ITEMS, "REMOVE", old=item)
    assert run(insert, modify_returned, already, remove) == {"batchItemFailures": []}
    assert match_rows(aws) == []


# ---- direction B ----------------------------------------------------------------------------

def test_direction_b_matches_tagged_items(aws):
    owner = new_id()
    queue = aws.subscribe_owner(owner)
    item = seed_item(aws)
    report = seed_report(aws, ownerId=owner)
    assert run(report_event(report))["batchItemFailures"] == []
    assert [r["itemId"] for r in match_rows(aws)] == [item["itemId"]]
    assert len(aws.messages(queue)) == 1


def test_direction_b_skips_pending_and_failed_items(aws):
    seed_item(aws, tagged=False)
    failed = seed_item(aws, tagged=False)
    aws.items.update_item(Key={"itemId": failed["itemId"]}, UpdateExpression="SET tagStatus = :f",
                          ExpressionAttributeValues={":f": "FAILED"})
    run(report_event(seed_report(aws)))
    assert match_rows(aws) == []


def test_direction_b_rereads_a_pending_index_row_and_uses_it_when_now_tagged(aws):
    """The index copy says PENDING but the table is TAGGED: the consistent read decides."""
    item = make_item()
    stale = {**item, "tagStatus": "PENDING"}
    stale.pop("clipTags")
    aws.items.put_item(Item=stale)  # the index copy is the stale one
    aws.items.put_item(Item=item)   # moto indexes are immediate, so emulate by patching the candidate list
    import matching

    original = matching._query_candidates
    matching._query_candidates = lambda *a, **k: [stale]
    try:
        run(report_event(seed_report(aws)))
    finally:
        matching._query_candidates = original
    assert [r["itemId"] for r in match_rows(aws)] == [item["itemId"]]


def test_direction_b_rereads_pending_and_skips_a_returned_item(aws):
    item = make_item(status="RETURNED")
    aws.items.put_item(Item=item)
    stale = {**make_item(itemId=item["itemId"]), "tagStatus": "PENDING"}
    import matching

    original = matching._query_candidates
    matching._query_candidates = lambda *a, **k: [stale]
    try:
        run(report_event(seed_report(aws)))
    finally:
        matching._query_candidates = original
    assert match_rows(aws) == []


def test_report_record_that_is_not_a_new_open_report_is_ignored(aws):
    seed_item(aws)
    report = make_report()
    modify = stream_record(REPORTS, "MODIFY", new=report, old=report)
    closed = make_report(status="CLOSED")
    insert_closed = stream_record(REPORTS, "INSERT", new=closed)
    assert run(modify, insert_closed) == {"batchItemFailures": []}
    assert match_rows(aws) == []


# ---- idempotency and races ------------------------------------------------------------------

def test_the_same_record_twice_sends_one_email(aws):
    owner = new_id()
    queue = aws.subscribe_owner(owner)
    seed_report(aws, ownerId=owner)
    event = tagged_event(seed_item(aws))
    run(event)
    run(event)
    assert len(match_rows(aws)) == 1
    assert len(aws.messages(queue)) == 1


def test_both_directions_find_the_same_pair_one_email(aws):
    owner = new_id()
    queue = aws.subscribe_owner(owner)
    report = seed_report(aws, ownerId=owner)
    item = seed_item(aws)
    run(tagged_event(item), report_event(report))
    assert len(match_rows(aws)) == 1
    assert len(aws.messages(queue)) == 1


def test_already_recorded_pair_never_republishes(aws, monkeypatch):
    owner = new_id()
    report = seed_report(aws, ownerId=owner)
    item = seed_item(aws)
    aws.matches.put_item(Item={"reportId": report["reportId"], "itemId": item["itemId"], "score": 1,
                               "scoreParts": {}, "why": ["x"], "createdAt": "2026-01-01T00:00:00.000Z"})
    import notify

    monkeypatch.setattr(notify, "sns_client", lambda: pytest.fail("must not publish"))
    run(tagged_event(item))
    assert match_rows(aws)[0]["score"] == 1  # untouched


# ---- SNS failure paths (6.7) ----------------------------------------------------------------

def _refuse(monkeypatch, error):
    import notify

    class Boom:
        def publish(self, **_):
            raise error

    monkeypatch.setattr(notify, "sns_client", lambda: Boom())


def test_sns_refusal_deletes_the_row_and_fails_the_record(aws, monkeypatch):
    seed_report(aws)
    _refuse(monkeypatch, ClientError({"Error": {"Code": "AuthorizationError", "Message": "no"}}, "Publish"))
    result = run(tagged_event(seed_item(aws), seq="77"))
    assert result == {"batchItemFailures": [{"itemIdentifier": "77"}]}
    assert match_rows(aws) == []  # undone, so the retry can record and send again


def test_request_never_reached_sns_also_deletes_and_fails(aws, monkeypatch):
    seed_report(aws)
    _refuse(monkeypatch, ConnectTimeoutError(endpoint_url="https://sns.us-east-2.amazonaws.com"))
    result = run(tagged_event(seed_item(aws), seq="78"))
    assert result["batchItemFailures"] == [{"itemIdentifier": "78"}]
    assert match_rows(aws) == []


def test_lost_answer_keeps_the_row_and_does_not_fail(aws, monkeypatch):
    seed_report(aws)
    _refuse(monkeypatch, ReadTimeoutError(endpoint_url="https://sns.us-east-2.amazonaws.com"))
    result = run(tagged_event(seed_item(aws)))
    assert result == {"batchItemFailures": []}
    rows = match_rows(aws)
    assert len(rows) == 1 and "notifiedAt" not in rows[0]


def test_retry_after_refusal_records_and_sends(aws, monkeypatch):
    owner = new_id()
    queue = aws.subscribe_owner(owner)
    seed_report(aws, ownerId=owner)
    event = tagged_event(seed_item(aws), seq="5")
    with monkeypatch.context() as m:
        _refuse(m, ClientError({"Error": {"Code": "Throttling", "Message": "slow"}}, "Publish"))
        assert run(event)["batchItemFailures"]
    assert run(event) == {"batchItemFailures": []}
    assert len(match_rows(aws)) == 1 and "notifiedAt" in match_rows(aws)[0]
    assert len(aws.messages(queue)) == 1


def test_one_failing_pair_does_not_stop_the_other_pairs(aws, monkeypatch):
    import notify

    owner_a, owner_b = new_id(), new_id()
    aws.subscribe_owner(owner_a)
    queue_b = aws.subscribe_owner(owner_b)
    seed_report(aws, ownerId=owner_a)
    seed_report(aws, ownerId=owner_b)
    real = notify.sns_client()

    class FailsForA:
        def publish(self, **kwargs):
            if kwargs["MessageAttributes"]["ownerId"]["StringValue"] == owner_a:
                raise ClientError({"Error": {"Code": "InternalError", "Message": "x"}}, "Publish")
            return real.publish(**kwargs)

    monkeypatch.setattr(notify, "sns_client", lambda: FailsForA())
    result = run(tagged_event(seed_item(aws), seq="9"))
    assert result["batchItemFailures"] == [{"itemIdentifier": "9"}]
    assert len(aws.messages(queue_b)) == 1
    assert [r["reportId"] for r in match_rows(aws)] and len(match_rows(aws)) == 1  # A's row was undone


def test_notified_at_failure_is_only_logged(aws, monkeypatch, caplog):
    import notify

    seed_report(aws)
    real_table = notify.matches_table

    class NoUpdate:
        def __init__(self, table):
            self._t = table

        def put_item(self, **kw):
            return self._t.put_item(**kw)

        def update_item(self, **kw):
            raise ClientError({"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "x"}}, "UpdateItem")

    monkeypatch.setattr(notify, "matches_table", lambda: NoUpdate(real_table()))
    with caplog.at_level("ERROR", logger="matcher"):
        assert run(tagged_event(seed_item(aws))) == {"batchItemFailures": []}
    assert "notifiedAt not saved" in caplog.text


# ---- robustness and logging -----------------------------------------------------------------

def test_malformed_and_foreign_records_are_skipped_not_failed(aws):
    bad_item = make_item(itemId="not-a-uuid")
    bad_report = make_report(ownerId="nope")
    foreign = stream_record("some-other-table", "INSERT", new=make_report())
    no_arn = {"eventName": "INSERT", "dynamodb": {"SequenceNumber": "1"}}
    result = run(tagged_event(bad_item), report_event(bad_report), foreign, no_arn)
    assert result == {"batchItemFailures": []}


def test_malformed_candidates_are_skipped(aws):
    good = seed_report(aws)
    aws.reports.put_item(Item=make_report(ownerId="not-a-uuid"))
    run(tagged_event(seed_item(aws)))
    assert [r["reportId"] for r in match_rows(aws)] == [good["reportId"]]


def test_candidate_cap_stops_at_500_and_warns(aws, caplog, monkeypatch):
    import matching

    monkeypatch.setattr(matching, "MAX_CANDIDATES", 5)
    monkeypatch.setattr(matching, "QUERY_PAGE_SIZE", 2)
    for i in range(8):
        seed_report(aws, colors=["red"], created_at=f"2026-10-20T18:00:0{i}.000Z")
    with caplog.at_level("WARNING", logger="matcher"):
        run(tagged_event(seed_item(aws)))
    assert "candidate cap" in caplog.text


def test_first_failed_record_stops_the_batch_and_is_the_only_one_reported(aws, monkeypatch):
    import notify

    seed_report(aws)
    _refuse(monkeypatch, ClientError({"Error": {"Code": "InternalError", "Message": "x"}}, "Publish"))
    first = tagged_event(seed_item(aws), seq="10")
    second = tagged_event(seed_item(aws), seq="11")
    assert run(first, second) == {"batchItemFailures": [{"itemIdentifier": "10"}]}


def test_logs_never_contain_email_or_message_body(aws, caplog):
    owner = new_id()
    aws.subscribe_owner(owner)
    seed_report(aws, ownerId=owner)
    item = seed_item(aws)
    with caplog.at_level("DEBUG"):
        run(tagged_event(item))
    text = caplog.text
    assert "outcome=notified" in text
    assert "@" not in text
    assert "Open https" not in text
    assert "description" not in text.lower()


def test_importing_the_modules_needs_no_environment(monkeypatch):
    for name in list(TEST_ENV):
        monkeypatch.delenv(name, raising=False)
    for module in ("app", "matching", "notify", "scoring", "clients", "settings"):
        __import__(module)


def test_missing_environment_variable_fails_the_record_loudly(aws, monkeypatch, caplog):
    monkeypatch.delenv("ALERTS_TOPIC_ARN")
    import settings
    settings.get_settings.cache_clear()
    with caplog.at_level("ERROR", logger="matcher"):
        result = run(report_event(make_report(), seq="3"))
    assert result == {"batchItemFailures": [{"itemIdentifier": "3"}]}
    assert "RuntimeError" in caplog.text


def test_published_attribute_is_a_string_ownerid(aws):
    owner = new_id()
    queue = aws.subscribe_owner(owner)
    seed_report(aws, ownerId=owner)
    run(tagged_event(seed_item(aws)))
    body = aws.messages(queue)[0]
    assert body["MessageAttributes"]["ownerId"]["StringValue"] == owner
    json.dumps(match_rows(aws), default=int)  # stored numbers are plain whole numbers
