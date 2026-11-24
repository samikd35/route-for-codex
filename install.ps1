# Install the Route CLI for the current Windows user, including from Windows PowerShell 5.1.
param([switch]$InstallOnly)
& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $arch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    switch ($arch) {
        'AMD64' { $target = 'x86_64-pc-windows-msvc'; $digest = 'edd61f7f5728a56cc62455386661860bdfc7bab65872f39b0c25bdcc1d8e1beb' }
        'ARM64' { $target = 'aarch64-pc-windows-msvc'; $digest = '72eed595983a4d7d22d79f21065b0f4479cc7e5c7a89104bb410c8f47559a878' }
        default { throw "Unsupported Windows processor: $arch" }
    }
    $tmp = New-Item -ItemType Directory -Path ([IO.Path]::Combine([IO.Path]::GetTempPath(), [guid]::NewGuid().ToString()))
    try {
        Write-Host 'Preparing the Route command-line installer...'
        $zip = Join-Path $tmp 'uv.zip'
        Invoke-WebRequest -UseBasicParsing "https://github.com/astral-sh/uv/releases/download/0.13.9/uv-$target.zip" -OutFile $zip
        if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne $digest) { throw 'uv download checksum mismatch' }
        Expand-Archive $zip (Join-Path $tmp 'uv')
        $uv = (Get-ChildItem (Join-Path $tmp 'uv') -Recurse -Filter 'uv.exe' -File).FullName
        $ref = if ($env:ROUTE_INSTALL_REF) { $env:ROUTE_INSTALL_REF } else { 'main' }
        if ($ref -notmatch '^[a-zA-Z0-9._-]+$') { throw 'Invalid Route revision' }
        $source = Join-Path $tmp 'source'
        $zip = Join-Path $tmp 'route.zip'
        Invoke-WebRequest -UseBasicParsing "https://codeload.github.com/samikd35/route-for-codex/zip/$ref" -OutFile $zip
        Expand-Archive $zip $source
        $entry = Join-Path (Get-ChildItem $source -Directory).FullName 'tools\install_cli.py'
        $options = @()
        if ($InstallOnly) { $options += '--install-only' }
        & $uv run --no-project --managed-python --python 3.13 -- python -I $entry $uv @options
        if ($LASTEXITCODE -ne 0) { throw "Route setup exited with code $LASTEXITCODE" }
        $env:Path = (Join-Path $env:LOCALAPPDATA 'RouteForCodexCLI\bin') + ';' + $env:Path
    } finally {
        Remove-Item -LiteralPath $tmp.FullName -Recurse -Force
    }
}
