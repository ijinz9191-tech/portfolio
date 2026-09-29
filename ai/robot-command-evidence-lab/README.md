# Robot Command Evidence Lab

An offline Python audit of **synthetic** robot command observations. It checks unique request IDs, the order of request, acceptance and completion, and overlapping commands for the same robot. A command without a completion observation is `EVIDENCE_GAP`; it is never presented as successful. An explicit observed failure stays `FAILED`. The output includes a SHA-256 digest of the canonical input.

```powershell
conda run -p <compatible-environment-prefix> python -B -m unittest discover -s tests -v
conda run -p <compatible-environment-prefix> python -B audit.py samples/commands.json
```

The exercise does not communicate with devices, certify operational safety, or represent work done for an employer. It demonstrates how a backend API could keep a request receipt separate from evidence of execution.
