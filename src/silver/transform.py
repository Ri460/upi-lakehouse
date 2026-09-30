from decimal import Decimal
import pandas as pd
from src.common.contract import canonical, normalize


def transform(records):
    unique = {}
    for raw in records:
        event = normalize(raw)
        key = event["txn_id"]
        if key in unique and canonical(unique[key]) != canonical(event):
            raise ValueError("conflicting txn_id in bronze")
        unique[key] = event
    if not unique:
        raise ValueError("empty batch: no publication")
    frame = pd.DataFrame(unique.values())
    frame["amount_paise"] = frame["amount"].map(lambda x: int(Decimal(x) * 100)).astype("int64")
    frame["amount"] = frame["amount"].astype(float)
    frame["event_ts"] = pd.to_datetime(frame["event_ts"], utc=True)
    frame = frame.sort_values(["user_id", "event_ts", "txn_id"]).reset_index(drop=True)
    # Baseline excludes the current transaction and future transactions.
    history = frame.groupby("user_id")["amount_paise"].transform(lambda s: s.shift().expanding().mean())
    frame["amount_spike"] = frame["amount_paise"] > 10 * history
    # Trailing 60-second count, including current timestamp; deterministic ties by txn_id.
    counts = pd.Series(index=frame.index, dtype="int64")
    for _, group in frame.groupby("user_id", sort=False):
        values = pd.Series(1, index=pd.DatetimeIndex(group["event_ts"]))
        counts.loc[group.index] = values.rolling("60s").sum().to_numpy()
    frame["velocity_flag"] = counts > 5
    frame["is_fraud"] = frame["amount_spike"] | frame["velocity_flag"]
    frame["dt"] = frame["event_ts"].dt.strftime("%Y-%m-%d")
    frame["hr"] = frame["event_ts"].dt.strftime("%H")
    frame["event_ts"] = frame["event_ts"].dt.tz_localize(None)
    frame["campaign_id"] = frame["campaign_id"].astype("string")
    return frame
