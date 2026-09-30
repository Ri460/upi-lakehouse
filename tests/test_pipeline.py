import base64
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pandas as pd
import pytest
from botocore.exceptions import ClientError
from src.common.contract import normalize, InvalidEvent
from src.producer.main import generate
from src.silver.transform import transform
from src.silver.quality import validate, require_pass
from src.validator import handler as validator


@pytest.fixture
def event():
    return next(generate(1, bad_rate=0, start=datetime(2026, 1, 1, tzinfo=timezone.utc)))[0]


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", None),
        ("amount", "-1"),
        ("amount", "nan"),
        ("amount", "0"),
        ("amount", "1.001"),
        ("event_ts", "2026-01-01"),
        ("payment_method", "bitcoin"),
        ("txn_id", "../escape"),
        ("schema_version", 3),
        ("currency", "USD"),
    ],
)
def test_contract_rejects(event, field, value):
    event[field] = value
    with pytest.raises(InvalidEvent):
        normalize(event)


def test_evolution(event):
    v1 = {**event, "schema_version": 1}
    v2 = {**event, "schema_version": 2, "campaign_id": "sale"}
    assert normalize(v1)["campaign_id"] is None
    assert normalize(v2)["campaign_id"] == "sale"


def test_replay_and_conflict(event):
    assert len(transform([event, event])) == 1
    with pytest.raises(ValueError, match="conflicting"):
        transform([event, {**event, "amount": "100.01"}])


def test_fraud_history_and_velocity(event):
    records = [
        {**event, "txn_id": f"t{i}", "amount": "1.00", "event_ts": f"2026-01-01T00:00:{i:02}+00:00"}
        for i in range(6)
    ]
    records += [{**event, "txn_id": "spike", "amount": "100.00", "event_ts": "2026-01-01T00:02:00+00:00"}]
    f = transform(records).set_index("txn_id")
    assert not f.loc["t0", "amount_spike"]
    assert f.loc["t5", "velocity_flag"]
    assert f.loc["spike", "amount_spike"]
    assert not f.loc["spike", "velocity_flag"]


def test_quality_gate(event):
    frame = transform([event])
    assert validate(frame)["success"]
    bad = pd.concat([frame, frame], ignore_index=True)
    bad.loc[0, "amount"] = -1
    report = validate(bad)
    with pytest.raises(ValueError, match="quality gate failed"):
        require_pass(report)


def record(event):
    return {"kinesis": {"sequenceNumber": "1", "data": base64.b64encode(json.dumps(event).encode()).decode()}}


@pytest.fixture
def services(monkeypatch):
    s3, sqs, table = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setenv("BUCKET", "test")
    monkeypatch.setenv("DLQ_URL", "queue")
    monkeypatch.setattr(validator, "clients", lambda: (s3, sqs, table))
    return s3, sqs, table


def test_invalid_routes_both_sinks(event, services):
    s3, sqs, _ = services
    assert validator.handler({"Records": [record({**event, "amount": None})]}, None) == {
        "batchItemFailures": []
    }
    assert s3.put_object.call_args.kwargs["Key"].startswith("quarantine/")
    sqs.send_message.assert_called_once()


def test_infra_failures_retry_not_quarantine(event, services):
    s3, sqs, table = services
    s3.put_object.side_effect = RuntimeError("S3 unavailable")
    assert validator.handler({"Records": [record(event)]}, None)["batchItemFailures"] == [
        {"itemIdentifier": "1"}
    ]
    sqs.send_message.assert_not_called()
    s3.put_object.side_effect = None
    assert validator.handler({"Records": [record(event)]}, None)["batchItemFailures"] == []
    assert table.update_item.called


def test_conflicting_id_is_quarantined(event, services):
    s3, sqs, table = services
    table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
    )
    assert validator.handler({"Records": [record(event)]}, None)["batchItemFailures"] == []
    assert s3.put_object.call_args.kwargs["Key"].startswith("quarantine/")


def test_replay_writes_same_key_and_bytes(event, services):
    s3, _, _ = services
    validator.handler({"Records": [record(event), record(event)]}, None)
    assert s3.put_object.call_args_list[0] == s3.put_object.call_args_list[1]


def test_gate_failure_does_not_publish(event, monkeypatch):
    import io
    from src.silver import handler as batch

    data = transform([event])
    data.loc[0, "amount"] = -1
    buf = io.BytesIO()
    data.to_parquet(buf, index=False)
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": io.BytesIO(buf.getvalue())}
    monkeypatch.setenv("BUCKET", "demo")
    monkeypatch.setenv("DATABASE", "demo")
    monkeypatch.setenv("SERVE_TABLE", "demo")
    monkeypatch.setattr(batch.boto3, "client", lambda *a, **k: s3)
    monkeypatch.setattr(batch.boto3, "resource", lambda *a, **k: MagicMock())
    with pytest.raises(ValueError, match="quality gate failed"):
        batch.handler({"run_id": "abc", "op": "gate"}, None)
    assert all(c.kwargs["Key"].startswith("quality/") for c in s3.put_object.call_args_list)


def test_publish_requires_pass_marker(monkeypatch):
    from src.silver import handler as batch

    s3 = MagicMock()
    s3.head_object.side_effect = RuntimeError("no PASSED marker")
    monkeypatch.setenv("BUCKET", "demo")
    monkeypatch.setenv("DATABASE", "demo")
    monkeypatch.setenv("SERVE_TABLE", "demo")
    monkeypatch.setattr(batch.boto3, "client", lambda *a, **k: s3)
    monkeypatch.setattr(batch.boto3, "resource", lambda *a, **k: MagicMock())
    with pytest.raises(RuntimeError, match="PASSED"):
        batch.handler({"run_id": "abc", "op": "publish"}, None)
    s3.get_object.assert_not_called()


def test_gold_success_revenue_only(event):
    import duckdb
    from src.common.gold import QUERIES

    f = transform(
        [
            {**event, "txn_id": "a", "amount": "1.11", "status": "SUCCESS"},
            {**event, "txn_id": "b", "amount": "9.99", "status": "FAILED"},
        ]
    )
    con = duckdb.connect()
    con.register("silver", f)
    rows = con.execute(QUERIES["daily_merchant_revenue"]).df()
    assert rows.iloc[0].revenue_paise == 111


def test_merchant_api_snapshot(monkeypatch):
    from src.api import handler as api

    table = MagicMock()
    table.get_item.side_effect = [{"Item": {"run_id": "r1"}}, {"Item": {"payload": '{"revenue_paise":111}'}}]
    db = MagicMock()
    db.Table.return_value = table
    monkeypatch.setattr(api.boto3, "resource", lambda *a: db)
    monkeypatch.setenv("SERVE_TABLE", "serve")
    result = api.handler({"routeKey": "GET /merchant/{id}/summary", "pathParameters": {"id": "m1"}}, None)
    assert result["statusCode"] == 200
    assert table.get_item.call_args.kwargs["Key"] == {"pk": "r1#m1"}


def test_live_producer_keeps_exact_duplicate_payload(monkeypatch):
    import sys
    import boto3
    from src.producer import main as producer

    client = MagicMock()
    monkeypatch.setattr(boto3, "client", lambda *a, **k: client)
    monkeypatch.setattr(producer.time, "sleep", lambda _: None)
    monkeypatch.setattr(sys, "argv", ["producer", "--stream", "demo", "--count", "100", "--bad-rate", ".9"])
    producer.main()
    seen = {}
    repeats = 0
    for call in client.put_record.call_args_list:
        item = json.loads(call.kwargs["Data"])
        if item["txn_id"] in seen:
            assert item == seen[item["txn_id"]]
            repeats += 1
        seen[item["txn_id"]] = item
    assert repeats > 0
