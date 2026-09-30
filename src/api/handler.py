import json
import os
from decimal import Decimal
import boto3


def response(code, body):
    return {
        "statusCode": code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, default=lambda x: float(x) if isinstance(x, Decimal) else str(x)),
    }


def handler(event, context):
    db = boto3.resource("dynamodb")
    route = event.get("routeKey", "")
    key = event.get("pathParameters", {}).get("id", "")
    if route == "GET /txn/{id}":
        item = (
            db.Table(os.environ["TXN_TABLE"]).get_item(Key={"txn_id": key}, ConsistentRead=True).get("Item")
        )
        if not item:
            return response(404, {"error": "transaction not found"})
        return response(
            200, {"transaction": json.loads(item["payload"]), "ingest_status": item["status_ingest"]}
        )
    if route == "GET /merchant/{id}/summary":
        table = db.Table(os.environ["SERVE_TABLE"])
        current = table.get_item(Key={"pk": "CURRENT"}, ConsistentRead=True).get("Item")
        item = (
            table.get_item(Key={"pk": f"{current['run_id']}#{key}"}, ConsistentRead=True).get("Item")
            if current
            else None
        )
        if not item:
            return response(404, {"error": "merchant summary not found"})
        return response(200, json.loads(item["payload"]))
    return response(404, {"error": "unknown route"})
