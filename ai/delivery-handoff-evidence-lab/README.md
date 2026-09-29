# Delivery Handoff Evidence Lab

An offline audit of **synthetic** last-mile delivery event evidence. Unlike the Delivery Command Ledger, which accepts and persists commands, this tool reviews an exported event stream for missing handoffs and hypothetical deadline outcomes. A completion with a missing pickup is labelled `EVIDENCE_GAP`, never "on time" or "late." Events require actor evidence and ordered integer minute timestamps. Duplicate deliveries/stages, impossible timestamps and malformed input fail closed. A canonical SHA-256 digest binds the review to its input.

```powershell
conda run -n base python -B -m unittest discover -s tests -v
conda run -n base python -B audit.py samples/routes.json
```

The fixture is local and invented. It does not connect to dispatch systems, maps, customers or the employer's data. An evidence gap may reflect incomplete logging rather than a failed physical handoff; deadlines are sample assumptions, not a measured SLA.
