param([Parameter(Mandatory)][string]$Artifact, [switch]$Uninstall)
$ErrorActionPreference = 'Stop'
if ($env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:GITHUB_ACTIONS -ne 'true') { throw 'Requires an unused hosted VM' }
$app = Join-Path $env:LOCALAPPDATA 'Programs\RouteForCodex'
$exe = Join-Path $app 'route.exe'
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'Route for Codex.lnk'
$login = Join-Path ([Environment]::GetFolderPath('Startup')) 'Route Login.lnk'
function Invoke-Installer([string]$Path) {
    $p = Start-Process -FilePath $Path -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Installer exited $($p.ExitCode)" }
}
function Get-LoginPath {
    [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
if ($Uninstall) {
    Invoke-Installer (Join-Path $app 'unins000.exe')
    if ((Test-Path $exe) -or (Test-Path $shortcut) -or (Test-Path $login) -or ((Get-LoginPath) -split ';' -contains "$app\bin")) {
        throw 'Uninstall left a launcher, executable or PATH entry'
    }
    exit 0
}
if ((Test-Path $app) -or (Test-Path "$HOME\.route") -or (Test-Path $shortcut) -or (Test-Path $login)) { throw 'Route already present' }
$packages = @(Get-ChildItem -LiteralPath $Artifact -Filter '*.exe' -File)
if ($packages.Count -ne 1) { throw 'Expected one Inno Setup package' }
Get-FileHash $packages[0].FullName -Algorithm SHA256 | Format-List
Invoke-Installer $packages[0].FullName
$shell = New-Object -ComObject WScript.Shell
foreach ($entry in @(@($shortcut, 'setup'), @($login, 'login'))) {
    $link = $shell.CreateShortcut($entry[0])
    if ($link.TargetPath -ne $exe -or $link.Arguments -ne $entry[1]) { throw "Wrong shortcut: $($entry[0])" }
}
# Resolve the command from the persisted PATH a new terminal receives.
$env:Path = Get-LoginPath
$where = & "$env:SystemRoot\System32\where.exe" route-for-codex
if ($LASTEXITCODE -ne 0 -or @($where)[0] -ne "$app\bin\route-for-codex.cmd") { throw 'Installed command missing from fresh PATH' }
$status = & $env:ComSpec /d /c 'route-for-codex status'
if ($LASTEXITCODE -ne 0 -or $status -ne 'Disconnected.') { throw 'First status was not Disconnected' }
Start-Process -FilePath $shortcut
Add-Type -Namespace RouteTest -Name Window -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet=System.Runtime.InteropServices.CharSet.Unicode)]
public static extern System.IntPtr FindWindow(string cls, string title);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern uint GetWindowThreadProcessId(System.IntPtr handle, out uint pid);
'@
$deadline = (Get-Date).AddSeconds(45)
do {
    $handle = [RouteTest.Window]::FindWindow('TkTopLevel', 'Route for Codex')
    if ($handle -ne [IntPtr]::Zero) {
        [uint32]$owner = 0
        [void][RouteTest.Window]::GetWindowThreadProcessId($handle, [ref]$owner)
        $process = Get-Process -Id $owner
        if ($process.Path -ne $exe) { throw 'Window came from another executable' }
        Stop-Process -InputObject $process
        $process.WaitForExit(5000) | Out-Null
        Write-Host 'Installed Route opened its setup window from Start.'
        exit 0
    }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)
throw 'Start shortcut did not open the Route setup window'
