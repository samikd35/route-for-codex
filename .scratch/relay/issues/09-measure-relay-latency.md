# 09. Measure the relay’s first-event overhead

Status: ready-for-agent

Blocked by: [01](01-verify-codex-tool-loop.md)

Spec: [Route v1 for Codex Desktop and CLI](../spec.md)

A developer qualifying an installation can reproduce Route’s latency measurement and distinguish relay overhead from model generation time.

## Acceptance criteria

- [x] Send matched pairs of identical requests from the same client to the same deterministic local streaming provider, directly and through bundled Caddy. Time from request send until receipt of the first complete stream event.
- [x] Compute relayed minus direct duration for each pair, then take the 95th percentile of those differences. The qualification check passes at or below 50 ms and reports failure above it.
- [ ] Report the sample count, timings, versions and OS so a release run is reproducible. Also compare time to first complete event and total duration for matched direct and relayed live requests. The 50 ms threshold applies to the deterministic local benchmark.

## Comments

`python -m tests.latency` measured 0.273 ms p95 across 40 paired requests on macOS 26.2 arm64. It reports raw pairs, versions and a failing exit code above 50 ms. The opt-in `--live` comparison has not been run.
