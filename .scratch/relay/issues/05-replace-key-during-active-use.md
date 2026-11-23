# 05. Replace the upstream key during an active session

Status: ready-for-agent

Blocked by: [03](03-connect-and-activate.md)

Spec: [Route v1 for Codex Desktop and CLI](../spec.md)

A developer can rotate the key while using either client. The replacement applies at the point of replacement, including when the provider rejects it.

## Acceptance criteria

- [ ] Hold a stream open with the old test credential. After replacement, allow that stream to finish and observe the replacement credential on every newly started request, including a tool-result follow-up from the same conversation and requests from the other client.
- [ ] Refresh discovery with the replacement credential and test only the selected model. Use the replacement for discovery and every connection-check request. Surface errors at the stage where they occur.
- [ ] Replace a working key with a rejected one. Verify that the error reaches the developer, the replacement stays selected, and subsequent requests never use the old credential. Inspect upstream observations with dummy credential identifiers.

## Comments

Bundled Caddy hot reload was observed to preserve an existing stream and use the replacement for new requests. Rejected discovery, session-only fallback and no reuse of stale storage have regression tests. Actual two-client credential rotation awaits qualification.
