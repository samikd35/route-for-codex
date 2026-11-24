# 04 — Guided setup and migration

Status: ready-for-agent

Blocked by: combined-picker/03

- [ ] Implement one-action GUI and route-for-codex, show the two-request cost, session-only option, actionable states and a verified Ready state.
- [x] After key verification, register the combined catalog automatically. Omit the default-provider question from terminal and GUI setup.
- [x] For a signed-in user, preserve the existing native model and reasoning effort. If Codex selected the model automatically, retain its native catalog default. Append the eligible branded Route rows.
- [x] For a user with only a project key, select an eligible Route row automatically. During upgrade from the old Route default, recover the pre-Route selection from the settings journal.
- [ ] Verify first installation and repeated setup in stock Desktop and CLI. Check the initially selected row, the labels for both billing paths, and the destination after switching rows in the same chat.
- [ ] Stage activation, resolve managed conflicts, safely migrate journaled values, and verify clean install, manual edits and crash recovery.
- [ ] Preserve legacy chats. Verify Disconnect, fresh-token Reconnect, and Forget.

## Comments

2026-11-23 · The Python package installs the route-for-codex entry point. Stock new chats selected either configured default without changing the three fixture rows. Guided activation, journal migration, and recovery of the combined provider remain open.

2026-11-24 · The source installer stages the Go dispatcher. The macOS integration test upgrades a disposable legacy profile, preserves its native selection, reads the branded picker rows in stock Codex, switches accounts twice in one chat and verifies the resulting file. Normally launched Desktop and release qualification remain open.
