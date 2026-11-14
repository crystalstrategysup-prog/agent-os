# AgentOS engineering verification strategy

## Checks
Use the registered rebuild-contracts, diagnostic-regression and compatibility-regression checks. Cover current and stale document pins, missing and invalid metadata, path traversal, symlinks, hard links where relevant, finite read/output limits, pending transactions and terminal task pointers. Assert no writes or command/network execution by diagnosis.
Exercise native Atlas and global-home facade routing while preserving explicit project selection. Run scoped transaction and recovery v3 positive/negative and interrupted-operation regressions after integration. Installer tests cover compatible activation, reader loss refusal, exact provenance and rollback.

## Evidence
Retain exact input/source hashes, tool versions, command arrays, exit status and bounded logs. Existing matching evidence is reusable at its original scope and time; changing source invalidates dependent results. The final review reads the actual diff. Build proof includes source commit, reviewed dirty-state policy, wheel payload and installed readback.

## Limitations
Synthetic tests establish their named contracts only. A private project inspection does not prove complete business coverage, throughput, access to a remote provider or acceptance by an already running client. Platform and external effects stay UNKNOWN until observed in their own scope.
