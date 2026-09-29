# Factory Event Evidence Lab

An offline audit for **synthetic** manufacturing handoff events. For each lot it verifies an ordered START/COMPLETE pair at every configured station. An unfinished sequence is reported as `EVIDENCE_GAP`; a skipped station, duplicate event, impossible order, or ambiguous timestamp is rejected. The output includes a SHA-256 digest of the canonical input for repeatable review.

```powershell
python ai/factory-event-evidence-lab/audit.py ai/factory-event-evidence-lab/samples/events.json
python -m unittest discover -s ai/factory-event-evidence-lab/tests -v
```

The sample is fabricated. This is a review aid for event consistency, not an MES integration, a quality verdict, or a record of work at a particular manufacturer. It cannot establish that a physical operation occurred; it only checks the supplied log.
