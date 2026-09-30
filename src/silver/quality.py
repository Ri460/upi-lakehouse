import great_expectations as gx


def validate(frame):
    context = gx.get_context(mode="ephemeral")
    context.enable_analytics(False)
    source = context.data_sources.add_pandas(name="silver")
    batch = (
        source.add_dataframe_asset(name="staged")
        .add_batch_definition_whole_dataframe("all")
        .get_batch(batch_parameters={"dataframe": frame})
    )
    rules = [
        gx.expectations.ExpectColumnValuesToNotBeNull(column=c)
        for c in ["txn_id", "user_id", "merchant_id", "amount", "event_ts", "payment_method"]
    ]
    rules += [
        gx.expectations.ExpectColumnValuesToBeUnique(column="txn_id"),
        gx.expectations.ExpectColumnValuesToBeBetween(column="amount", min_value=0, strict_min=True),
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="payment_method", value_set=["UPI", "card", "wallet"]
        ),
    ]
    results = [batch.validate(rule).to_json_dict() for rule in rules]
    report = {"success": all(r["success"] for r in results), "checks": results, "rows": len(frame)}
    return report


def require_pass(report):
    if not report["success"]:
        raise ValueError("Great Expectations quality gate failed; silver not published")
