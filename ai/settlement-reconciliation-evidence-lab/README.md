# Settlement Reconciliation Evidence Lab

An offline Python exercise for comparing a synthetic posting ledger with a
synthetic merchant settlement batch. Each transaction ID must appear exactly
once on each side with the same merchant and signed integer amount. The report
separates a missing settlement, an unmatched settlement, and a changed amount
or merchant. A canonical SHA-256 digest binds the inspected input evidence.

```powershell
python -B reconcile.py samples/match.json
python -B -m unittest discover -s tests -v
```

The exit code is `0` for a complete match, `1` when review is required, and
`2` for malformed input. The sample is made up. This program neither moves
money nor connects to PAYCO, a bank, or a past employer system. It supports an
engineering discussion about the evidence needed before a settlement can be
called reconciled; it is not proof of financial-domain production experience.
