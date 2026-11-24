# Route for Codex

Route lets you use your OpenAI project key for coding and image generation in local Codex sessions. It runs on your computer. Your project pays for model and image requests. The signed-out macOS CLI has passed the live image check on Sol and Astra. [Qualification record](docs/qualification.md)

## Install and connect from the terminal

In your project folder, run the same command in macOS Terminal or Windows PowerShell. It uses Node.js with npm (`npx`) and Git to start the installer from this GitHub repository.

```sh
npx samikd35/route-for-codex
```

If npm asks to install the package, answer **y**. Route installs its runtime and adds the official Codex CLI if it is missing. To install now and connect later, use `npx samikd35/route-for-codex --install-only`.

<details>
<summary>Install on a computer without Node.js or Git</summary>

**macOS Terminal**

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/samikd35/route-for-codex/main/install.sh)"
```

**Windows PowerShell**

```powershell
Invoke-RestMethod https://raw.githubusercontent.com/samikd35/route-for-codex/main/install.ps1 | Invoke-Expression
```

</details>

1. Paste your OpenAI project API key at the private terminal prompt. Route checks model access and verifies the connection with two billable model requests.
2. Answer **y** to **Use Route by default for new Codex sessions?** and wait for **Connection test passed.**
3. Answer **y** to open Codex in the current folder. Later, open a fresh terminal in any project and run `codex`.

The install runs under your user account. It leaves the system networking command `route` available. Route uses Keychain or Windows Credential Manager for the key and offers session-only use when secure storage is unavailable. Your OpenAI project pays for requests sent through Route.

| From a fresh terminal | Command |
| --- | --- |
| Finish or retry terminal setup | `route-for-codex onboard` |
| Check whether the relay is running | `route-for-codex status` |
| Change the API key | `route-for-codex replace` |
| Restore your previous Codex settings | `route-for-codex disconnect` |
| Restart the CLI-installed relay after login | `route-for-codex reconnect` |
| Disconnect and remove the locally saved key | `route-for-codex forget` |

To install only, add `-- --install-only` after the macOS command. On Windows run `& ([scriptblock]::Create((Invoke-RestMethod https://raw.githubusercontent.com/samikd35/route-for-codex/main/install.ps1))) -InstallOnly`. Rerun the installer for updates. The desktop development packages are also available from the [installer workflow](https://github.com/samikd35/route-for-codex/actions/workflows/build-installers.yml), including an unsigned Apple Silicon package, a Windows x64 installer and a Debian package. See the [qualification record](docs/qualification.md) for platform coverage.

## Run from source

Use Python 3.11+ with Tk (3.13+ on Windows), a recent Codex CLI with `codex debug models --bundled`, and Homebrew on Apple Silicon macOS or Go on other build hosts. The macOS and Linux commands below create a private Python environment inside your clone.

```sh
git clone https://github.com/samikd35/route-for-codex.git
cd route-for-codex
python3 tools/install.py --connect
codex
```

Keep the checkout in place. Codex launches Route from that environment. Omit `--connect` to install without entering a key. On Apple Silicon, if the Homebrew bottle has moved on, add `--from-go` with Go installed. On Windows, clone the same repository and from PowerShell in the checkout run:

```powershell
py -3.13 tools\install.py --connect
codex
```

For the setup window on macOS or Linux, run `.venv/bin/route-for-codex setup`. On Windows use `.\.venv\Scripts\route-for-codex.exe setup`. Use `select` to choose another eligible model and `test` to repeat verification. To run the source tests, use `.venv/bin/python -m unittest discover -v`. They use temporary profiles and dummy credentials. The coding fixture runs the actual Codex executable.

The upstream key goes to the OS credential store, or remains in relay memory for a session-only connection. The credential helper reads only a local token from the private Route directory. Caddy consumes its configuration on stdin, disables config persistence and emits no request logs. Rotation reloads it via a private filesystem socket. `CODEX_HOME` selects the Codex profile; `ROUTE_HOME` selects private Route state (default `~/.route`). These overrides do **not** isolate the OS keychain: use a separate OS account for live qualification. Disconnect or Forget before removing an installed build.

The [combined-picker proof](docs/combined-picker-proof.md) runs separately in a disposable profile. The current setup command still registers the legacy Route provider.

## Generate an image using only your API key

1. If Route is already connected, continue to step 2. Otherwise run `route-for-codex onboard` and choose Route for new chats. Your key needs access to the selected coding model and `gpt-image-2`.
2. Run `codex` in a project folder. Ask **Use Route’s generate_image tool to create a red kite above a blue lake. Save it as kite.png and make an index.html that displays it.** Approve the tool call if prompted. Each generation uses your OpenAI project.
3. Open the resulting `index.html` and confirm the illustration is visible. The [repeatable image check and results](docs/api-key-only-images.md) include the exact qualification prompt and verified image hashes.

## Development installers

```sh
.venv/bin/python -m pip install 'pyinstaller>=6.12,<7'
.venv/bin/python tools/package.py
```

Build on the target OS. macOS produces an unsigned `.pkg` with Route.app, a CLI and a login agent. Debian produces a `.deb` with an application menu entry, XDG login entry and `/usr/bin/route-for-codex`. Windows uses Go, Python 3.13+ and Inno Setup `ISCC` to build a per-user installer with Start menu and login shortcuts. An editable source installation supports the `login` action when explicitly invoked.

The Linux container build uses digest-pinned Python and Caddy images, runs relay and lifecycle tests, and installs the Debian package in the container to check its terminal command. From a fresh checkout:

```sh
docker buildx build --output type=local,dest=dist -f tools/linux.Dockerfile .
```

For design and acceptance criteria, see [architecture](ARCHITECTURE.md), [spec](.scratch/relay/spec.md), and [tickets](.scratch/relay/issues/).

The [installer workflow](https://github.com/samikd35/route-for-codex/actions/workflows/build-installers.yml) builds development packages after packaging or application changes on `main`. Sign in to GitHub, open a successful run, and download the artifact for your platform. Maintainers can also start a build manually. The stable release will include the qualified native packages and their SHA-256 checksums together once each supported client and OS passes the [release checks](docs/qualification.md).

Route source is licensed under [MIT](LICENSE). The bundled Caddy relay carries its own [Apache 2.0 license](route/bin/LICENSE).
