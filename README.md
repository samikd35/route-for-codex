# Route for Codex

Route lets you use your OpenAI project key for coding and image generation in local Codex sessions. It runs on your computer. Your project pays for model and image requests. The signed-out macOS CLI has passed the live image check on Sol and Astra. [Qualification record](docs/qualification.md)

## Install and connect

Route is in development. Testers can use a development installer built for their OS and processor. A public stable release is pending. Install a compatible Codex client first. The CLI used for qualification was `0.171.0-alpha.13`; to check your CLI, run `codex --version` and `codex debug models --bundled`.

| Platform | With the development installer | Status |
| --- | --- | --- |
| Apple Silicon Mac | Open the Route `.pkg` and follow Installer. Open **Route** in Applications. | Unsigned development package. |
| Debian 13 | From the download directory, run `sudo apt install ./route-dev-aarch64.deb` on arm64. Open **Route for Codex** from the application menu. | Container-tested. Graphical qualification is pending. |
| Windows | Once a native build is available, run `Route-dev-setup.exe` and open **Route for Codex** from Start. | Installer recipe available. Native qualification is pending. |

In Route, paste your OpenAI project key, leave **Use Route for new Codex chats** selected, and click **Connect to Codex**. Verification uses two billable model requests. Once the connection test passes, start a **new local chat** in Codex. For example, open a project and ask “Which command runs this project’s tests?”

For terminal setup, open a **fresh terminal** after installing and run the following as your regular user:

```sh
route-for-codex connect
route-for-codex status
codex
```

At the private key prompt, enter your key and agree to use Route by default. Later, `route-for-codex disconnect` restores your previous Codex settings, `reconnect` uses your saved key, and `forget` deletes Route’s saved key from this computer.

## Run from source

Use Python 3.11+ with Tk (3.13+ on Windows), a recent Codex CLI with `codex debug models --bundled`, and Homebrew on Apple Silicon macOS or Go on other build hosts. The macOS and Linux commands below create a private Python environment inside your clone.

```sh
git clone https://github.com/samikd35/route-for-codex.git
cd route-for-codex
python3 -m venv .venv
.venv/bin/python tools/bundle.py
.venv/bin/python -m pip install -e .
.venv/bin/route-for-codex connect
codex
```

On Apple Silicon, if the Homebrew bottle has moved on, use `.venv/bin/python tools/bundle.py --from-go` with Go installed. On Windows, clone the same repository and from PowerShell in the checkout run:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe tools\bundle.py
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\route-for-codex.exe connect
codex
```

For the setup window, use `setup` in place of `connect`. Use `select` to choose another eligible model and `test` to repeat verification. To run the source tests, use `.venv/bin/python -m unittest discover -v`. They use temporary profiles and dummy credentials. The coding fixture runs the actual Codex executable.

The upstream key goes to the OS credential store, or remains in relay memory for a session-only connection. The credential helper reads only a local token from the private Route directory. Caddy consumes its configuration on stdin, disables config persistence and emits no request logs. Rotation reloads it via a private filesystem socket. `CODEX_HOME` selects the Codex profile; `ROUTE_HOME` selects private Route state (default `~/.route`). These overrides do **not** isolate the OS keychain: use a separate OS account for live qualification. Disconnect or Forget before removing an installed build.

The [combined-picker proof](docs/combined-picker-proof.md) runs separately in a disposable profile. The current setup command still registers the legacy Route provider.

## Generate an image using only your API key

1. From this checkout, run `.venv/bin/route-for-codex connect`, enter your project key and select **Use Route by default**. If you already connected with the previous source build, install the updated dependencies with `uv pip install -e .` and run `.venv/bin/route-for-codex reconnect` to register the image tool. The key needs access to the selected coding model and `gpt-image-2`.
2. Restart Codex and open a fresh local workspace. Choose Sol or Astra from the Route provider. In either client, ask **Use Route’s generate_image tool to create a red kite above a blue lake. Save it as kite.png and make an index.html that displays it.** Approve the tool call if prompted. Each generation uses your API project.
3. Open the resulting `index.html` and confirm the illustration is visible. The [repeatable image check and results](docs/api-key-only-images.md) include the exact qualification prompt and verified image hashes.

## Development installers

```sh
.venv/bin/python -m pip install 'pyinstaller>=6.12,<7'
.venv/bin/python tools/package.py
```

Build on the target OS. macOS produces an unsigned `.pkg` with Route.app, a CLI and a login agent. Debian produces a `.deb` with an application menu entry, XDG login entry and `/usr/bin/route-for-codex` (so it doesn't shadow the system network utility). Windows uses Go, Python 3.13+ and Inno Setup `ISCC` to build a per-user installer with Start menu and login shortcuts; that build is unverified. In development environments the `login` action can be exercised explicitly; no login hook is installed by editable installation.

The Linux container build uses digest-pinned Python and Caddy images, runs relay and lifecycle tests, and extracts the Debian package to check its executable. From a fresh checkout:

```sh
docker buildx build --output type=local,dest=dist -f tools/linux.Dockerfile .
```

For design and acceptance criteria, see [architecture](ARCHITECTURE.md), [spec](.scratch/relay/spec.md), and [tickets](.scratch/relay/issues/).

Maintainers can run **Build development installers** in GitHub Actions to build test artifacts. Distribute the qualified native packages and their SHA-256 checksums together in a versioned GitHub Release once each supported client and OS passes the [release checks](docs/qualification.md).

Route source is licensed under [MIT](LICENSE). The bundled Caddy relay carries its own [Apache 2.0 license](route/bin/LICENSE).
