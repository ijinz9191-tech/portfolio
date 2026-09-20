# Verification

The verifier runs javac --release 21 and java -ea -cp .build lab.GatewayTest. Its report contains compile/test exit codes, actual UTC time, Java version, test output and per-Java-file SHA-256. source_hash hashes sorted path:sha256 lines separated by LF without a trailing newline.

The test suite exercises prediction and validation, idempotency conflicts, feature-copy isolation, TTL expiry, queue saturation, capacity, transient retry, breaker open/probe/recovery, invalid model results, draining/cancellation, explicitly ephemeral restart behavior and actual localhost HTTP calls.

Logical clocks make cache and breaker tests deterministic. Latches control worker failure and saturation. The HTTP integration test uses Java HttpClient against a real local server, not a mocked status response.

This evidence covers source and tests, not remote Git publication or deployment. No production load benchmark, threat-model certification, actual AI model quality or applicant employment experience is inferred. Rerun after Java changes; documentation changes alone do not alter the Java source fingerprint.
