import argparse
import gzip
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
import duckdb
from src.common.contract import InvalidEvent, canonical, digest, normalize, partition
from src.common.gold import QUERIES
from src.producer.main import generate
from src.silver.transform import transform
from src.silver.quality import validate, require_pass


def run(root, count=5000):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    valid, rejected, duplicates, injected, ids = [], [], 0, {}, {}
    latencies = []
    events = list(generate(count, start=datetime(2026, 9, 1, tzinfo=timezone.utc)))
    for event, issue in events:
        injected[issue or "clean"] = injected.get(issue or "clean", 0) + 1
        t0 = time.perf_counter()
        try:
            item = normalize(event)
            if item["txn_id"] in ids:
                if ids[item["txn_id"]] != digest(item):
                    raise InvalidEvent("conflicting ID")
                duplicates += 1
                continue
            ids[item["txn_id"]] = digest(item)
            valid.append(item)
            path = root / "bronze" / partition(item) / (item["txn_id"] + ".ndjson.gz")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress((canonical(item) + "\n").encode(), mtime=0))
            latencies.append((time.perf_counter() - t0) * 1000)
        except InvalidEvent as e:
            rejected.append({"reason": str(e), "event": event})
    (root / "quarantine.json").write_text(json.dumps(rejected, indent=2))
    frame = transform(valid)
    report = validate(frame)
    (root / "quality.json").write_text(json.dumps(report, indent=2, default=str))
    require_pass(report)
    import shutil

    if (root / "silver").exists():
        shutil.rmtree(root / "silver")
    frame.to_parquet(root / "silver", partition_cols=["dt", "hr"], index=False, compression="snappy")
    replay = transform(valid + valid)
    assert len(replay) == len(frame)
    con = duckdb.connect()
    con.register("silver", frame)
    gold = {name: con.execute(sql).df().to_dict("records") for name, sql in QUERIES.items()}
    for name, rows in gold.items():
        (root / f"{name}.json").write_text(json.dumps(rows, indent=2))
    parquet_size = sum(p.stat().st_size for p in (root / "silver").rglob("*.parquet"))
    json_size = sum(len(canonical(e).encode()) + 1 for e in valid)
    malformed = sum(v for k, v in injected.items() if k not in ["clean", "duplicate"])
    metrics = {
        "source": "LOCAL synthetic demo; not AWS performance or cost",
        "python": platform.python_version(),
        "input_events": count,
        "accepted_unique": len(frame),
        "invalid_rejected": len(rejected),
        "duplicates_removed": duplicates,
        "injected": injected,
        "bad_record_catch_rate": len(rejected) / malformed if malformed else None,
        "replay_duplicates": len(replay) - replay.txn_id.nunique(),
        "local_ingest_p95_ms": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 3),
        "total_demo_seconds": round(time.perf_counter() - started, 3),
        "json_bytes": json_size,
        "partitioned_parquet_bytes": parquet_size,
        "storage_reduction_pct": round((1 - parquet_size / json_size) * 100, 2),
        "aws_events_per_minute": None,
        "aws_p95_latency_ms": None,
        "athena_bytes_scanned": None,
        "aws_cost_usd": None,
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Local synthetic demo",
        "metrics": metrics,
        **gold,
    }
    (root / "dashboard.json").write_text(json.dumps(payload, indent=2))
    (root / "benchmarks.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    return payload


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=5000)
    p.add_argument("--out", default="data/demo")
    a = p.parse_args()
    run(a.out, a.count)
