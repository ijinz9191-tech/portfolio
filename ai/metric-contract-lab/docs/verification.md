# Verification

Run python -B scripts/verify.py. It executes unittest in a subprocess and records actual UTC execution time, environment, exit code, test output and a SHA-256 manifest of Python files in artifacts/verification.json. This binds implementation, tests and scripts; it is neither a signature nor a hash of every document.

Run python -B scripts/run_demo.py for a deterministic synthetic before/late/rebuild demonstration. artifacts/demo-result.json captures its real output. The logical clock is fixture input, not execution time.

Tests use real temporary SQLite databases, an actual loopback HTTP server and subprocess CLI calls. Failure injection adds a temporary trigger only to an isolated test database, asserts transaction rollback, removes that injected trigger and checks recovery. It does not weaken production checks.

No remote application, cloud deployment or third-party API is mocked as successful. Success does not establish production scalability, high availability, authentication, comprehensive security, user employment experience or application acceptance. No performance improvement percentage is claimed.

Rerun after any Python source change. Git publication and remote version verification are separate steps; local artifacts do not assert either.
