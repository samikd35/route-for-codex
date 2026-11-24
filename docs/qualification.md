# Development evidence

This is not a release announcement. Local fixture passes, a working installer payload, and live Codex qualification are separate milestones.

| Target | Observed in this workspace | Still required |
| --- | --- | --- |
| macOS 26.2 arm64 | Caddy 2.11.9, Codex CLI 0.171.0-alpha.13. Real CLI credential helper, streamed tool calls, verified workspace change and resume. Signed-out CLI generated and rendered images with Sol and Astra. Extracted development installer ran the stdio image tool. | Fresh signed installer, normal-launch Codex Desktop, login lifecycle, Desktop Stop and the remaining live matrix. See the separate hosted installer fixture below. |
| Debian 13 arm64 container | Relay authorization, streamed key rotation, setup challenge and mocked-store connection lifecycle passed. `.deb` built and its extracted executable ran. | Native desktop session, actual Secret Service, login, real clients and the complete release matrix. |
| Windows | The [GitHub Actions build](https://github.com/samikd35/route-for-codex/actions/runs/45238433188) produced a per-user Windows development installer. The package includes the Credential Manager backend, socket control helper, Start menu shortcut, and a terminal launcher. | Interactive key entry in the GUI, live clients, restart and Windows 11 desktop qualification. See the hosted Server 2025 installer result below. |

Development build: `0.1.0.dev0`. Initial macOS deterministic latency run: 40 alternating-order pairs, **0.273 ms p95** relayed-minus-direct time to first complete SSE event (limit 50 ms). `python -m tests.latency` emits per-pair first-event/total times, versions, sample count and pass/fail. These results do not measure OpenAI latency. `python -m tests.latency --live --pairs 3` explicitly opts into six paid requests, prompts for a key and reports a comparison, not a local threshold verdict.

`tests/test_client_interrupt.py` also drove the real macOS `codex exec`: SIGINT closed the upstream stream before completion, and an upstream drop after a tool call produced `turn.failed` with exactly one upstream request. This is not a test of the Desktop Stop button.

The Linux Caddy binary extracted from the development `.deb` measured **0.140 ms p95** over 40 local pairs in an offline Debian arm64 container (LinuxKit 6.10.14, glibc 2.41, Python 3.13.18). This is container evidence, not a native Linux desktop qualification.

## Combined picker development results

On November 23, 2026, the macOS CLI displayed both billing paths in its stock picker, completed live Sol and Astra coding tasks across account switches and resumed after manual compaction. Its built-in image tool produced a workspace PNG on each model, and Chrome rendered both generated pages. These observations used the development dispatcher. The earlier development installer still configures the single-provider relay. The [proof and reproduction instructions](combined-picker-proof.md) record scope and remaining checks. Raw evidence is kept in the local checkout.

On November 24, 2026 the public npx installer upgraded an existing macOS connection to Route `0.1.0.dev3` using the saved verification receipt. The CLI launcher and Desktop bundle both reported `0.171.0-alpha.13`. The running CLI app-server reported `0.172.0`. Its visible list went from ten native models to ten native and seven Route models after registering the matching catalog and reloading the provider. The real terminal `/model` menu displayed both Sol and Astra on both billing paths. The Desktop bundle returned the same 17 visible rows through `model/list`; a separate visual inspection of the Desktop dropdown remains open. A gateway started with only the older catalog built the newer catalog on demand. The four macOS and Windows terminal installer fixtures passed. [Installer checks](https://github.com/samikd35/route-for-codex/actions/runs/45319339190)

On November 24, 2026 a local build fixed the `Unsupported Codex version` response on a gateway with both installed catalogs. The Desktop engine `0.171.0-alpha.13` and managed CLI service `0.172.0` each completed ordinary Sol and Route Sol turns through that gateway with fixture credentials. A separate live run created native Sol chats before installing the build, then resumed each chat with its original ID. Ordinary Sol completed after installation. Route 6.2 Sol then recalled a different code from each chat's first turn. The API relay recorded successful project-key requests during each switch, and its upstream credential matched the saved key. The live run used `codex exec resume` and the running Desktop app's connector. Graphical model selection remains open.

## API-key-only image results

The normal Route provider now registers its own `generate_image` tool. In an isolated macOS CLI profile, `codex login status` reported signed out. With only the existing Route project key, Sol and Astra each generated one PNG. Each workspace copy matched the private Route artifact byte for byte, and Chrome displayed both pages. Qualification is open for signed-out Desktop on macOS and both clients on Windows and Linux. [Versions, prompt, results and reproduction steps](api-key-only-images.md)

## Repeat the release checks

1. Use a clean test account. Install the native artifact, launch Route normally, and connect with a project key. Verify the model and effort in Desktop from its launcher and in a new CLI terminal. Repeat with a different model subset and with no default Sol. Record OS, Route/Caddy and both Codex versions. Never attach configuration dumps, keys, or unredacted provider logs.
2. For each of `desktop` and `cli`, and each of `gpt-6.2-sol` and `gpt-6.2-astra`, run `python -m tests.live prepare /path/to/run --client desktop --model gpt-6.2-sol --effort medium` with the corresponding values. Each combination gets **separate fresh coding and image workspaces**; reuse is rejected. Select that model and effort in the client. Run the printed prompts. Record the actual selection and the follow-up answer against the fixture value.
3. Run `python -m tests.live verify` with the same arguments. It checks the unchanged test, input value, repaired file, PNG and page. Open `image/index.html` in a browser, verify the generated local PNG loads and is visible, and capture the rendered page. File presence alone is not an image pass. Record each combination independently. Missing access is an unqualified combination, not a pass.
4. Exercise saved-key, session-only, failed key replacement, manual config edits, Disconnect, Reconnect, Forget, and locked-store restart on the real OS. Check that an explicit Disconnect survives login and that a same-key reconnect does not issue a probe. Repeat setup from the other entry point. The mocked-store suite does not qualify the actual keychain or login manager.
5. `tests/test_interrupt.py` verifies downstream disconnect, an incomplete upstream stream after a tool call, no relay replay, explicit retry and concurrent request isolation. It is a transport check. Run `python -m tests.controls stop /path/to/new-fixture` and launch the client with the printed disposable `CODEX_HOME`. Send a prompt, press Stop before 30 seconds, and observe the disconnect count. Repeat with `drop` and a fresh directory: expect a client interruption after the tool call, one upstream request, and a second request only after explicit retry. Repeat from both clients. Run the local and live benchmarks separately and retain their JSON.

Qualify a platform only after every required check passes there. The deterministic fixtures use dummy credentials. The live image checks above used billable OpenAI requests and an isolated Codex configuration.

## Terminal-only installation

On November 24, 2026 the public terminal commands installed Route and OpenAI Codex CLI `0.171.0-alpha.13` on fresh macOS 26.7.2 arm64 and Windows Server 2025 x64 runners. Both discovered the command on the persistent PATH, recovered a dummy key from the native store, completed the setup challenge, and checked the exact reply from signed-out Codex through a local Responses fixture. Repeating the default installer reached the private key prompt and cancelled cleanly. Windows used Windows PowerShell 5.1 and PowerShell 7. This run used no live API credential. [Terminal installation run](https://github.com/samikd35/route-for-codex/actions/runs/45307759320)

## Fresh macOS and Windows installer checks

Both clean-machine fixtures passed on November 23, 2026, using stock Codex CLI `0.171.0-alpha.13`. The live-key steps were skipped on this run. The production package still uses the single Route provider. [Full workflow run](https://github.com/samikd35/route-for-codex/actions/runs/45247655313)

| Fresh runner | Observed result | Installer SHA-256 |
| --- | --- | --- |
| [macOS 26.7.2 arm64](https://github.com/samikd35/route-for-codex/actions/runs/45247655313/job/137950533799) | Applications launch, login-shell command, Keychain recovery, signed-out CLI reply, Forget and missing-pip regression passed. | `7ca284157ab53892a5f3f24ab259b827c91522cde652b98c71d18876d3fa3baa` |
| [Windows Server 2025 x64, build 26100](https://github.com/samikd35/route-for-codex/actions/runs/45247655313/job/137951183483) | Start launch, fresh PATH, private directory validation, Credential Manager recovery, signed-out CLI reply, Forget, uninstall and missing-pip regression passed. | `70451bceb057e3ccbc6be69cae5671a0ac748ad66a750ccf9e901af2274f88d9` |

The installer workflow downloads the exact build artifact on a second GitHub-hosted VM for each OS. The test installs the package, resolves `route-for-codex status` using the login PATH, opens the installed setup window, and runs a signed-out stock Codex CLI. Each run logs the package SHA-256, OS, architecture and CLI version. Windows also checks uninstall and PATH removal. Both runners exercise the missing-pip source-install regression.

- The default run enters a dummy key through the installed `connect` command. A loopback proxy refuses model discovery before any request reaches OpenAI. The test checks that the Codex default survived the failure and that Disconnect, Reconnect and Forget work with the native credential store. It then supplies a synthetic catalog and credential to the packaged Caddy and exercises the installed `test` command, default registration, a fresh Codex turn and `forget`. It makes no billable requests.
- For real first-time setup, set the repository Actions secret `ROUTE_INSTALL_TEST_KEY` to a dedicated test-project key with access to `gpt-6.2-sol`. In **Actions → Build development installers → Run workflow**, choose `main` and enable **Perform billable API-key qualification on both fresh runners**. Each platform runs the installed `connect` command, completes the two-request challenge, disconnects, recovers the key from the native credential store, and checks the exact answer to a new Codex prompt. Budget for at least three model requests per platform. A missing secret fails the requested live check.
- The setup window check opens Route through Applications or Start. Interactive key entry in that window and a chat inside Codex Desktop remain separate manual qualifications. macOS signing and notarization also remain open.

[Installer runs and artifacts](https://github.com/samikd35/route-for-codex/actions/workflows/build-installers.yml)
