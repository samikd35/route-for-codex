# 03. Install and connect entirely in the terminal

Status: ready-for-agent

Blocked by: None for the development source installer.

- [x] Provide one public install command in macOS Terminal and Windows PowerShell.
- [x] Install the runtime and compatible Codex CLI when needed, prompt privately, verify Route, and offer to launch Codex.
- [x] Exercise the public command, persisted PATH and a signed-out Codex reply through the installed relay on each OS.

## Comments

The command installs the public source snapshot under the current user. Native package release qualification continues under distribution/01.

2026-11-24 · Both [fresh CLI installs](https://github.com/samikd35/route-for-codex/actions/runs/45307759320) passed key prompting, credential recovery, a signed-out fixture reply, cancellation and repeat installation.

2026-11-24 · The GitHub-backed `npx` command and the direct installers passed on fresh macOS and Windows runners. All four jobs checked command discovery, a signed-out Codex fixture reply and cancellation at the private key prompt. [Test run](https://github.com/samikd35/route-for-codex/actions/runs/45309585249)

2026-11-24 · The terminal wizard shows download progress, verifies prebuilt gateways, resumes verified connections, and offers private key retries and a project-aware Codex launch. The installer supports `--verbose` and plain output when redirected.
