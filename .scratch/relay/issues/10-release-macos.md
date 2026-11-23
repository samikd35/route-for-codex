# 10. Package and qualify Route for macOS

Status: ready-for-agent

Blocked by: [05](05-replace-key-during-active-use.md), [06](06-recover-at-login.md), [07](07-propagate-stop-and-interruptions.md), [08](08-qualify-live-coding-and-images.md), [09](09-measure-relay-latency.md)

Spec: [Route v1 for Codex Desktop and CLI](../spec.md)

A macOS developer can install Route and use an independently qualified release in Desktop or CLI. Complete the native installer, per-user service, credential-store and login integration for the supported macOS environment.

## Acceptance criteria

- [ ] On a clean macOS installation, connect from the setup window and terminal. Launch Codex Desktop normally and CLI from a fresh terminal. Verify both see the eligible model/effort catalog and use the same relay after opt-in activation.
- [ ] Exercise key replacement with an active stream and a rejected replacement, settings restoration after manual edits, fresh-token reconnect, Forget, and session-only operation. Test login with saved, explicitly disconnected, session-only, and locked-store states.
- [ ] Pass the Stop and partial-stream interruption checks from both clients. Pass the live coding and rendered-image checks with GPT‑6.2 Sol and Astra in each client.
- [ ] Run the paired 50 ms p95 benchmark on macOS and record its result. Publish platform readiness with the tested OS, Route and Codex versions and evidence only after every required check passes. Qualification is independent of the other two operating systems.

## Comments

Unsigned arm64 development `.pkg` built. `tools/smoke_pkg.py` tested the executable and Caddy in the extracted payload without installing it. Clean install, live clients, actual login and keychain checks pending. Not released.
