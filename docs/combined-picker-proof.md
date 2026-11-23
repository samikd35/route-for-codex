# Combined Codex picker proof

## Run the stock-client fixture

From the Route checkout on macOS, use the project's Python environment, its pinned Caddy binary, Go 1.23 or newer, and a stock Codex executable on PATH.

```sh
proof_dir="$(mktemp -d)"
(cd dispatcher && go build -o "$proof_dir/route-dispatcher" .)
.venv/bin/python -m tests.combined --dispatcher "$proof_dir/route-dispatcher"
```

The fixture starts Caddy on a randomly assigned loopback port. An authenticated catalog endpoint on the Go dispatcher serves three rows. Two independent HTTP upstreams validate credential headers and outgoing model IDs. Both receive only synthetic credentials. The fixture starts a fresh app-server process after compaction, resumes the original chat ID, checks its retained tool results and verifies the file in the workspace. The shell-tool fixture uses conventional tool metadata. The live CLI run keeps the installed model metadata.

To inspect the actual terminal picker, append `--interactive` and enter `/model`. To test the executable included with Desktop, pass its absolute path with `--codex`. The latter runs the app-server protocol.

## Normally launched Desktop

Use a disposable OS user that has never launched Codex. Build the dispatcher in that user's checkout as above, then run the following command **before launching Desktop**. The fixture requires a new directory and exits if it already exists.

```sh
.venv/bin/python -m tests.combined --dispatcher "$proof_dir/route-dispatcher" --desktop-home "$HOME/.codex"
```

Launch Desktop using Finder in this test account. Open the workspace printed by the fixture and start one chat. Capture its chat ID and picker. Follow the terminal prompts to select each row, edit and verify the fixture, compact, close Desktop, and resume. Record the actual chat ID and recalled value before and after each switch. On exit the harness removes the two fixture configuration and authentication files if their contents still match. Codex may leave session data inside the disposable account.

On the development Mac, the ready-to-run fixture is in `/Users/Shared/Route-Picker-Proof-20261123`. The disposable user can double-click **Start Desktop Check.command** in Finder. That copy uses the CLI bundled with the installed ChatGPT app and the system Python.

## Live CLI

The live run requires an existing connected Route relay with access to the selected model and a Codex-managed ChatGPT sign-in. It sends billable requests to both accounts and saves a new test chat. CLI settings are process-local. The project key stays in the existing relay. The fixture obtains only Route's local token from its helper.

```sh
.venv/bin/python -m tests.combined_live --dispatcher "$proof_dir/route-dispatcher" --live
```

The CLI uses the authenticated catalog during inference. For the separate manual compaction RPC, the app-server process receives a temporary model metadata file to avoid the old installation's global catalog override. Codex performs its custom-provider local compaction and the subsequent CLI processes resume the same chat. The gate covers local summarization and replay. Server-only response, conversation and item IDs are rejected. Opaque inline content is preserved and an upstream refusal is returned to the caller.

Use `--model gpt-6.2-astra` to repeat with Astra. The optional `--image /absolute/path/to/a/new/workspace` runs the built-in image tool check independently. Verify the resulting page in a real browser and retain its screenshot. Run `go test -race ./...` inside `dispatcher/` for the billing-boundary and cancellation checks. The [feature tracker](../.scratch/combined-picker/spec.md) lists remaining release gates.

The combined transport can also be checked from the project root with the following commands.

```sh
ROUTE_PROOF_DISPATCHER="$proof_dir/route-dispatcher" .venv/bin/python -m unittest -v tests.test_client_interrupt
.venv/bin/python -m tests.latency --combined-dispatcher "$proof_dir/route-dispatcher" --pairs 40
```
