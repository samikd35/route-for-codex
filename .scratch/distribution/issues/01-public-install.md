# 01. Publish the source and distribute native installers

Status: ready-for-agent

Blocked by: None for source publication. The coordinated binary release depends on combined-picker/06.

- [x] Prepare a Git source tree, an open-source license for review, and exclusions for credentials, local session evidence, and generated installers.
- [x] Document first install and register the same terminal command in the three installer recipes.
- [x] Add a first-run key field and a manual GitHub workflow for building development installers.
- [ ] Select the GitHub owner and license and publish the source.
- [ ] Run the workflow on GitHub. Verify native install, fresh-terminal discovery, GUI setup and uninstall on each supported OS.
- [ ] Sign and notarize the macOS build, review third-party distribution notices, and publish the qualified packages together with checksums.

## Comments

2026-11-23 · Development packages and fixture tests are tracked separately from the public release. The [qualification record](../../../docs/qualification.md) lists the open client checks.
