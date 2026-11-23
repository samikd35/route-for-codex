# 02 — Same-chat switching

Status: ready-for-human

Blocked by: combined-picker/01

- [x] Exercise native → Route → native on one chat ID. Read a fresh value, edit and run a test, and recall the result from history.
- [x] Repeat after compaction and after closing and resuming. Independently verify the edit and tool call IDs, including an account-bound continuation case.
- [ ] Pass with actual credentials on both stock clients.

## Comments

2026-11-23 · Both live CLI model pairs passed an independent edit check and recall on the original chat ID after compaction and resume. Deterministic tests verify call IDs, reject account-scoped references, and propagate an opaque-item rejection without switching accounts. Desktop remains open. [Qualification record](../../../docs/qualification.md)
