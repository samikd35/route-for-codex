# 03. Install and connect entirely in the terminal

Status: ready-for-agent

Blocked by: None for the development source installer.

- [x] Provide one public install command in macOS Terminal and Windows PowerShell.
- [x] Install the runtime and compatible Codex CLI when needed, prompt privately, verify Route, and offer to launch Codex.
- [x] Exercise the public command, persisted PATH and a signed-out Codex reply through the installed relay on each OS.

## Comments

The command installs the public source snapshot under the current user. Native package release qualification continues under distribution/01.

2026-11-24 · Both [fresh CLI installs](https://github.com/samikd35/route-for-codex/actions/runs/45307759320) passed key prompting, credential recovery, a signed-out fixture reply, cancellation and repeat installation.

2026-11-24 · Add a single GitHub-backed `npx` command for Mac and Windows. Retain the direct installers for machines without Node.js or Git. Exercise both paths on fresh runners.
