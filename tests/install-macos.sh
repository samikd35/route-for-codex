#!/bin/bash
# Run only on an unused GitHub-hosted macOS VM.
set -euo pipefail
[[ ${RUNNER_ENVIRONMENT:-} == github-hosted && ${GITHUB_ACTIONS:-} == true ]]
app=/Applications/Route.app
cli=/usr/local/bin/route-for-codex
agent=/Library/LaunchAgents/local.route.login.plist
[[ ! -e $app && ! -e $cli && ! -L $cli && ! -e $agent && ! -e ~/.route ]]
packages=("$1"/*.pkg)
[[ ${#packages[@]} == 1 && -f ${packages[0]} ]]
shasum -a 256 "${packages[0]}"
sudo installer -pkg "${packages[0]}" -target /
[[ -x $app/Contents/MacOS/route && -L $cli && -f $agent ]]
[[ "$(readlink "$cli")" == "$app/Contents/MacOS/route" ]]
[[ "$(/usr/libexec/PlistBuddy -c 'Print ProgramArguments:1' "$agent")" == login ]]
# A fresh login shell must find the launcher without inheriting a build PATH.
env PATH=/usr/bin:/bin:/usr/sbin:/sbin /bin/zsh -lc \
  '[[ "$(command -v route-for-codex)" == /usr/local/bin/route-for-codex && "$(route-for-codex status)" == Disconnected. ]]'
open -n "$app"
swift - <<'SWIFT'
import AppKit
import CoreGraphics
import Foundation

let deadline = Date().addingTimeInterval(45)
while Date() < deadline {
    let apps = NSRunningApplication.runningApplications(withBundleIdentifier: "local.route.setup")
    let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
    for app in apps where app.bundleURL?.path == "/Applications/Route.app" {
        if windows.contains(where: { ($0[kCGWindowOwnerPID as String] as? Int32) == app.processIdentifier && ($0[kCGWindowLayer as String] as? Int) == 0 }) {
            app.terminate()
            print("Installed Route opened a window from Applications.")
            exit(0)
        }
    }
    Thread.sleep(forTimeInterval: 0.25)
}
fatalError("No on-screen Route window appeared")
SWIFT
