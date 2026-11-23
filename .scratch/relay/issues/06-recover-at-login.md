# 06. Restore the intended connection state at login

Status: ready-for-agent

Blocked by: [04](04-disconnect-reconnect-and-forget.md)

Spec: [Route v1 for Codex Desktop and CLI](../spec.md)

After a restart, Route resumes the developer’s last intended connection and handles a locked credential store without interrupting login.

## Acceptance criteria

- [ ] Leave Route connected with a saved key and log in again. It resumes with a fresh token and skips the two-request connection test. Open Desktop normally and verify a new CLI session can also use it.
- [ ] Repeat after an explicit Disconnect with the key still saved. The relay stays off. Repeat after session-only use. The prior connection ends and connecting again requires a key.
- [ ] Lock the credential store before automatic reconnect. Route shows **Waiting for unlock** without prompting at login. If still locked on next use, offer the OS unlock prompt. Once unlocked, resume with the saved key.

## Comments

Implemented `route login`, platform startup entries, noninteractive saved-key retrieval and waiting state. An explicit Disconnect and session-only state are covered by fixture tests. Actual reboot, locked-store and unlock prompts remain OS-level checks.
