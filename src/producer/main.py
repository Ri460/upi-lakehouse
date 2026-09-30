import argparse
import json
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def generate(count=1000, seed=42, bad_rate=0.03, start=None):
    rng = random.Random(seed)
    start = start or datetime.now(timezone.utc)
    previous = None
    for i in range(count):
        event = dict(
            txn_id=str(uuid.UUID(int=rng.getrandbits(128))),
            user_id=f"u{rng.randrange(100):03}",
            merchant_id=f"m{rng.randrange(12):03}",
            amount=f"{rng.randint(100, 500000) / 100:.2f}",
            currency="INR",
            payment_method=rng.choice(["UPI", "UPI", "card", "wallet"]),
            status=rng.choices(["SUCCESS", "FAILED", "PENDING"], [90, 7, 3])[0],
            city=rng.choice(["Hyderabad", "Bengaluru", "Mumbai"]),
            device_id=f"d{rng.randrange(500)}",
            event_ts=(start + timedelta(milliseconds=i * 100, hours=i // 500)).isoformat(),
            schema_version=1,
        )
        if i % 10 == 0:
            event.update(schema_version=2, campaign_id="festival-sale")
        issue = None
        if rng.random() < bad_rate:
            issue = rng.choice(["null_amount", "negative_amount", "bad_timestamp", "duplicate"])
            if issue == "null_amount":
                event["amount"] = None
            elif issue == "negative_amount":
                event["amount"] = "-12.00"
            elif issue == "bad_timestamp":
                event["event_ts"] = "not-a-date"
            elif previous:
                event = previous.copy()
            else:
                issue = None
        if issue is None:
            previous = event.copy()
        yield event, issue


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=1000)
    p.add_argument("--rate", type=float, default=20)
    p.add_argument("--bad-rate", type=float, default=0.03)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--stream")
    p.add_argument("--queue-url")
    p.add_argument("--output", default="data/events.ndjson")
    a = p.parse_args()
    if a.count < 1 or a.rate <= 0 or not 0 <= a.bad_rate <= 1 or (a.stream and a.queue_url):
        p.error("positive count/rate required; bad-rate 0..1; select one AWS sink")
    if a.stream or a.queue_url:
        import boto3

        client = boto3.client(
            "kinesis" if a.stream else "sqs", region_name=os.getenv("AWS_REGION", "ap-south-1")
        )
        # One event/request makes pacing explicit; SDK retries transient service errors.
        sent = {}
        for event, issue in generate(a.count, a.seed, a.bad_rate):
            if issue == "duplicate" and event["txn_id"] in sent:
                event = sent[event["txn_id"]].copy()
            else:
                event["event_ts"] = (
                    datetime.now(timezone.utc).isoformat()
                    if event["event_ts"] != "not-a-date"
                    else event["event_ts"]
                )
                sent[event["txn_id"]] = event.copy()
            if a.stream:
                client.put_record(
                    StreamName=a.stream, Data=json.dumps(event).encode(), PartitionKey=event["user_id"]
                )
            else:
                client.send_message(QueueUrl=a.queue_url, MessageBody=json.dumps(event))
            time.sleep(1 / a.rate)
    else:
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        Path(a.output).write_text(
            "".join(json.dumps(e) + "\n" for e, _ in generate(a.count, a.seed, a.bad_rate))
        )
    print(json.dumps({"submitted": a.count, "sink": a.stream or a.queue_url or a.output}))


if __name__ == "__main__":
    main()
