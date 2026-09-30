# Three-minute demo recording guide

This is a recording plan; no AWS demo video is claimed to exist yet.

**0:00–0:25 — Problem and architecture.** Show the architecture. Explain streaming validated events, a batch quality gate and analytics that remain viewable after AWS teardown. Call the data synthetic.

**0:25–0:55 — Ingestion.** Run the producer at 20 events/sec with 3% fault injection. Show bronze objects and a quarantine pointer. Explain that malformed data is quarantined while infrastructure errors retry.

**0:55–1:25 — Quality and replay.** Show the passing pytest suite, especially gate-failure and replay tests. Start a real Step Functions execution and show Stage → QualityGate → PublishSilver → Gold. Do not label unit tests as a cloud fault-injection demo.

**1:25–1:55 — Analytics and serving.** Show the Athena gold tables and the SigV4 merchant endpoint. Revenue excludes FAILED/PENDING payments; all amounts are INR and sums use integer paise. Explain heuristic flags.

**1:55–2:25 — Dashboard.** Export and publish the snapshot. Show merchant sorting, payment mix, flagged rates, and the AWS/local label. Make clear that it is an exported snapshot, not a real-time fraud dashboard.

**2:25–3:00 — Evidence and cost.** Show actual AWS p95, Athena scanned-byte comparison, and Billing total once measured. Show teardown complete and the GitHub Pages dashboard still open. Until AWS runs exist, present only the local metrics and explicitly label them local.

Record with OBS or your screen recorder at 1080p. Hide AWS account details and credentials. Put the video link in README once uploaded. A truthful local-only walkthrough is also useful, but should not imply the AWS system was deployed.
