# 04. Disconnect, reconnect, and forget a saved key

Status: ready-for-agent

Blocked by: [03](03-connect-and-activate.md)

Spec: [Route v1 for Codex Desktop and CLI](../spec.md)

A developer can leave Route, restore prior Codex settings, reconnect in one action, or remove the saved credential from the device.

## Acceptance criteria

- [ ] Disconnect stops the relay and invalidates its local token. Restore each changed setting only if its current value still equals what Route wrote. Test with an originally absent setting and a model selection the developer edited afterward.
- [ ] For a saved key, show “Disconnected. Your API key is saved on this device.” with Reconnect and Forget API key. Reconnect starts the relay with a fresh local token. The previous token is rejected.
- [ ] With the same saved key, reconnect makes zero inference requests until a real request or explicit Test connection. A later access error appears on that request.
- [ ] Disconnecting a session-only connection discards its key and reconnecting requires entry again. Forget API key disconnects an active connection, deletes the local saved copy, and does not revoke the upstream key.

## Comments

`tests/test_setup.py` exercises restoration, later edits, fresh-token reconnect, no inference on same-key reconnect, and Forget with a mocked native store. Native OS deletion/session-only qualification is pending.
