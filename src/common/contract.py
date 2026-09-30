import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

KEYS = ["txn_id", "user_id", "merchant_id", "currency", "payment_method", "status", "city", "device_id"]


class InvalidEvent(ValueError):
    pass


def normalize(raw):
    if not isinstance(raw, dict):
        raise InvalidEvent("event must be an object")
    out = {}
    for key in KEYS:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 100:
            raise InvalidEvent(f"invalid {key}")
        out[key] = value
    for key in ("txn_id", "user_id", "merchant_id"):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", out[key]):
            raise InvalidEvent(f"unsafe {key}")
    if out["currency"] != "INR":
        raise InvalidEvent("only INR supported; never aggregate mixed currencies")
    if out["payment_method"] not in ["UPI", "card", "wallet"]:
        raise InvalidEvent("invalid payment_method")
    if out["status"] not in ["SUCCESS", "FAILED", "PENDING"]:
        raise InvalidEvent("invalid status")
    try:
        amount = Decimal(str(raw["amount"]))
        if not amount.is_finite() or not 0 < amount <= 10000000 or amount != amount.quantize(Decimal(".01")):
            raise InvalidEvent("amount must be positive, <= 10000000, with <=2 decimals")
    except (KeyError, InvalidOperation, ValueError, TypeError) as e:
        raise InvalidEvent("invalid amount") from e
    out["amount"] = format(amount.quantize(Decimal(".01")), "f")
    version = raw.get("schema_version")
    if type(version) is not int or version not in (1, 2):
        raise InvalidEvent("unsupported schema_version")
    out["schema_version"] = version
    try:
        ts = datetime.fromisoformat(raw["event_ts"].replace("Z", "+00:00"))
        if ts.tzinfo is None:
            raise ValueError("timezone required")
        ts = ts.astimezone(timezone.utc)
        if ts.year < 2020 or ts.year > 2100:
            raise ValueError("timestamp outside demo contract")
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise InvalidEvent("invalid event_ts") from e
    out["event_ts"] = ts.isoformat(timespec="milliseconds")
    campaign = raw.get("campaign_id") if version == 2 else None
    if campaign is not None and (not isinstance(campaign, str) or len(campaign) > 100):
        raise InvalidEvent("invalid campaign_id")
    out["campaign_id"] = campaign
    return out


def canonical(event):
    return json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(event):
    return hashlib.sha256(canonical(event).encode()).hexdigest()


def partition(event):
    ts = datetime.fromisoformat(event["event_ts"])
    return f"dt={ts:%Y-%m-%d}/hr={ts:%H}"
