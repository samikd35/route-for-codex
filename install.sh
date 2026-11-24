#!/bin/sh
# Install the Route CLI for the current macOS user.
set -eu
case "$(uname -s):$(uname -m)" in
    Darwin:arm64) target=aarch64-apple-darwin; digest=5aeca67f2283f75235de40d0bd9c0a5bbc5fce23b6d48b3bf9fa1b2db08382ca ;;
    Darwin:x86_64) target=x86_64-apple-darwin; digest=617a3211261b0fc739562f0071aa34e9739797c510208ede8e2977c30903d041 ;;
    *) echo 'Use install.sh on macOS or install.ps1 on Windows.' >&2; exit 1 ;;
esac
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
download() { curl --proto '=https' --fail --silent --show-error --location --retry 2 "$1" -o "$2"; }
echo 'Preparing the Route command-line installer…'
download "https://github.com/astral-sh/uv/releases/download/0.13.9/uv-$target.tar.gz" "$tmp/uv.tar.gz"
printf '%s  %s\n' "$digest" "$tmp/uv.tar.gz" | shasum -a 256 -c -
tar -xzf "$tmp/uv.tar.gz" -C "$tmp" "uv-$target/uv"
uv="$tmp/uv-$target/uv"
ref=${ROUTE_INSTALL_REF:-main}
case "$ref" in *[!a-zA-Z0-9._-]*) echo 'Invalid Route revision' >&2; exit 1 ;; esac
download "https://codeload.github.com/samikd35/route-for-codex/tar.gz/$ref" "$tmp/route.tar.gz"
mkdir "$tmp/source"
tar -xzf "$tmp/route.tar.gz" --strip-components=1 -C "$tmp/source"
"$uv" run --no-project --managed-python --python 3.13 -- python -I "$tmp/source/tools/install_cli.py" "$uv" "$@"
