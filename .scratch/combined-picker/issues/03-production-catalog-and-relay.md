# 03 — Production catalog and relay

Status: ready-for-agent

Blocked by: combined-picker/01, combined-picker/02

- [ ] Preserve effective native account metadata and version-specific ordering. Append only eligible Route aliases; restrict upgrades to the same billing path.
- [ ] Authenticate and dispatch behind Caddy on a private local connection. Pin upstream and credentials per request, rotate keys, and reject unknown or revoked aliases.
- [ ] Cover streaming, cancellation, concurrent chats, errors, privacy and absence of cross-account fallback.

## Comments

2026-11-23 · The prototype implements authenticated versioned catalogs, alias translation, separate accounts, SSE, cancellation, private key/catalog rotation, and turn-scoped image billing. Stock CLI fixtures and Go race tests pass. Connect to effective native-provider discovery, key replacement and version refresh in the installation lifecycle before marking production complete.
