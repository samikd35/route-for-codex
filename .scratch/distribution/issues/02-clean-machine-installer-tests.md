# 02. Verify the public installers on fresh macOS and Windows machines

Status: ready-for-human

Blocked by: None for the fixture runs. The live runs require a dedicated test-project key in GitHub Actions.

- [x] Build on native workers and install the resulting packages on separate hosted VMs.
- [x] Test terminal command discovery, the first-run setup window, a signed-out Codex CLI turn and settings restoration.
- [x] Provide an opt-in check of first-time key entry, native credential recovery and a live Codex reply.
- [x] Record passing fixture runs on both platforms.
- [ ] Record passing live runs on both platforms.

## Comments

The [qualification guide](../../../docs/qualification.md#fresh-macos-and-windows-installer-checks) describes the entry points and evidence.

2026-11-23 · [Both clean-machine fixtures passed](https://github.com/samikd35/route-for-codex/actions/runs/45247655313) after fixing Windows private directory creation. The maintainer selected fixture checks first. The remaining live checks require the dedicated test secret and a manual dispatch.
