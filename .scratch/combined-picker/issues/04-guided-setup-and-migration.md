# 04 — Guided setup and migration

Status: ready-for-agent

Blocked by: combined-picker/03

- [ ] Implement one-action GUI and route-for-codex, show the two-request cost, session-only option, actionable states and a verified Ready state.
- [ ] Preserve the preferred model and provide a row-only default toggle.
- [ ] Stage activation, resolve managed conflicts, safely migrate journaled values, and verify clean install, manual edits and crash recovery.
- [ ] Preserve legacy chats. Verify Disconnect, fresh-token Reconnect, and Forget.

## Comments

2026-11-23 · The Python package installs the route-for-codex entry point. Stock new chats selected either configured default without changing the three fixture rows. Guided activation, journal migration, and recovery of the combined provider remain open.
