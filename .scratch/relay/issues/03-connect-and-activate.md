# 03. Connect once and activate Route for Desktop and CLI

Status: ready-for-agent

Blocked by: [01](01-verify-codex-tool-loop.md), [02](02-discover-eligible-models.md)

Spec: [Route v1 for Codex Desktop and CLI](../spec.md)

A developer installs the local connection on one development host using Connect in the setup window or `route connect` in a terminal. Both entry points share the preset upstream, credentials, and provider registration.

## Acceptance criteria

- [ ] From a clean profile, each entry point accepts the upstream key as the only required credential. Bind the key to the preset upstream in the OS credential store. When secure storage is unavailable, offer session-only use with the key in memory.
- [ ] Start the per-user relay on loopback and register one provider that both clients can use. A credential helper yields only the local token. Verify access from a normally launched Desktop app and a new terminal.
- [ ] Run the connection check only for the selected model. Two inference requests through the relay must carry a setup tool call and its matching output. Success requires the exact freshly generated value in the completed answer. The check uses no shell command or project file.
- [ ] A failed check shows the error. A passing check offers **Use Route by default**. Selecting it activates new sessions in both clients and records previous values, including absent settings, for restoration. Declining preserves the existing default.
- [ ] Verify that an unavailable model leaves the developer’s selection intact and allows an explicit choice. Distinguish a stopped relay, rejected key, and rate limit without logging credentials or request contents.

## Comments

Shared GUI/CLI actions, native storage, command-backed auth, the two-request challenge, and opt-in settings are implemented. A real CLI used the credential helper without a token environment variable. Normal Desktop launch and native keychain acceptance are pending.
