# 07. Propagate Stop and report interrupted streams

Status: ready-for-agent

Blocked by: [01](01-verify-codex-tool-loop.md)

Spec: [Route v1 for Codex Desktop and CLI](../spec.md)

A developer can stop a running request from either client and see when a provider stream breaks. Exercise the real client and relay with a controllable streaming provider.

## Acceptance criteria

- [ ] Start a long response, press Stop in Desktop, and verify that the provider observes the upstream disconnect before finishing. Repeat from CLI.
- [ ] Drop the upstream connection after a tool call has been forwarded but before the stream completes. Each client must detect the interruption. Provider observations show that Route initiates no replay.
- [ ] Distinguish an explicit client retry from a relay replay in the check. Cancellation or failure of one request leaves a concurrent independent request able to finish.

## Comments

`tests/test_interrupt.py` passed at the transport boundary. `python -m tests.controls` supplies an interactive deterministic Stop/drop provider. Actual Stop controls and interrupted turns need client evidence, not just the HTTP test.

`tests/test_client_interrupt.py` now demonstrates cancellation by SIGINT and interrupted-turn detection with no replay in real macOS `codex exec`. Desktop and interactive Stop acceptance remain open.
