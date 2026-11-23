# 01. Complete a coding task through bundled Caddy

Status: ready-for-human

Blocked by: None.

Spec: [Route v1 for Codex Desktop and CLI](../spec.md)

A developer can run a real Codex CLI session against a Route relay and get a verified workspace change. Use a deterministic Responses test provider so this check can run without a paid key.

## Acceptance criteria

- [x] Run the bundled Caddy on loopback under the developer’s account. An invalid local token is rejected before the provider sees the request. With a valid token, the provider receives its own credential and the expected model request body.
- [x] From a clean fixture, have the real CLI read a fresh random value, fix a failing test, run it to a pass, and answer a follow-up that depends on the earlier tool result. Assert the file change and test outcome independently of the assistant’s final text.
- [x] Demonstrate that the client receives an event before the provider finishes streaming. The provider receives the matching tool-call ID on continuation. A provider error preserves its upstream status.
- [x] Run the check a second time with a fresh fixture and local token. Generated configuration and logs contain neither credential, and default diagnostics omit request bodies and tool output.

## Comments

The pre-spec draft included live Desktop and CLI qualification. Ticket 08 owns those runs with GPT‑6.2 Sol and Astra. Tickets 10–12 require the evidence on each release platform.

Ready for acceptance review: `tests/test_codex.py` and `tests/test_relay.py` pass on macOS arm64; versions and scope in `docs/qualification.md`.
