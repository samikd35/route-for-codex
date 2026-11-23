# Image generation with a Route project key

## Live results on November 23, 2026

macOS 26.2 arm64, Route 0.1.0.dev0, Caddy 2.11.9, Codex CLI 0.171.0-alpha.13. A temporary Codex home used file-based auth storage and `codex login status` reported signed out. The CLI received no API-key environment variable. The normal Route `reconnect` action retrieved the previously saved project key and registered the provider and MCP tool against a separate local relay. Each run used the `route` provider, medium reasoning effort, and its own fresh workspace. The tool was `mcp__route_images__generate_image`. The coding model orchestrated the task and `gpt-image-2` generated the PNG.

| Client and model | Image and page | Workspace SHA-256 or remaining check |
| --- | --- | --- |
| macOS CLI · GPT-6.2 Sol | Passed. The 1329 × 1183 workspace PNG matched Route’s saved artifact by SHA-256 and loaded in Chrome. | `7530b6edafbb5c32334b78153f0e271432bd3c4de2207ded3d1f9ea6e09eebd5` |
| macOS CLI · GPT-6.2 Astra | Passed. The 1198 × 1313 workspace PNG matched Route’s saved artifact by SHA-256 and loaded in Chrome. | `fb79e97160d13f4a9694a5f30e92c8ed70505db5d128121071d66d5e69b32f09` |
| macOS Desktop · Sol and Astra | Pending for both in a normally launched, signed-out Desktop session. | Previous Desktop testing exercised the Codex built-in image tool. |
| Windows and Linux · Desktop and CLI | Pending on both models. | Native client and installer checks remain open. |

The live runs used a source installation and an existing saved key. The initial Connect flow was exercised with fixture credentials. The unsigned macOS development package was built and its extracted executable was tested for MCP discovery and the stopped-relay error. An installed-package live run is still due. The combined provider also has a separate [signed-in built-in image check](combined-picker-proof.md).

## Repeat from Desktop or an interactive CLI

1. Use a test OS account with a fresh, signed-out Codex profile. Run one Route relay on the machine’s configured port. Install the current Route development build and open its setup window, or run `.venv/bin/route-for-codex connect` from the prepared checkout. Enter a project key with access to the coding model and `gpt-image-2`. Complete the two-request verification and choose **Use Route by default**. To upgrade an existing connection from source, reinstall the dependencies and run `.venv/bin/route-for-codex reconnect`.
2. Run `.venv/bin/python -m tests.live prepare /path/to/run --client desktop --model gpt-6.2-sol --effort medium`. For CLI use `--client cli`. Launch Desktop from the OS launcher or CLI from a fresh terminal and open the generated `image` workspace. Select the specified Route provider model and medium effort. Keep Codex signed out. Use this exact prompt in a fresh chat.

   > Use Route's generate_image MCP tool (server route_images) to generate one PNG illustration of a red kite above a blue lake. Copy the returned file to kite.png in the current workspace and create a minimal index.html that displays kite.png. If the tool fails, report its error and stop without retrying or using a different image tool.

3. Approve the tool call when prompted. Record the invoked server and tool, client version, model, and effort. Independently decode `kite.png` and compare its SHA-256 with the staged PNG at the path returned by the tool. Open `index.html` in a browser, confirm the local image is visible, and capture the page. Repeat in a new workspace with `--model gpt-6.2-astra`. For the full coding-and-image matrix, complete the companion coding fixture before running `tests.live verify`.

The live CLI helper automates the signed-out profile, generation and hash check for both models. It needs a key already saved by Route. It allows just this image tool for each noninteractive test invocation. Open each resulting `index.html` for the browser check. Use a new output directory each time. The live command makes billable requests.

```sh
.venv/bin/python -m tests.key_only_images --live /absolute/path/to/new-run
```

The deterministic suite exercises the actual stdio entry point, loopback authentication, running-relay upgrade, cancellation, and settings restoration. The package smoke check launches the executable from the extracted macOS payload.

```sh
.venv/bin/python -m unittest discover -v
.venv/bin/python tools/package.py
.venv/bin/python tools/smoke_pkg.py dist/Route-dev-arm64.pkg
```
