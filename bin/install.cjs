#!/usr/bin/env node
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const args = process.argv.slice(2);
const usage = 'Usage: npx samikd35/route-for-codex [--install-only] [--verbose]';
if (args.length === 1 && ['--help', '-h'].includes(args[0])) {
  console.log(usage);
  process.exit(0);
}
if (args.some(arg => !['--install-only', '--verbose'].includes(arg))) {
  console.error(usage);
  process.exit(2);
}

const root = path.resolve(__dirname, '..');
let shell;
let options;
const env = { ...process.env };
if (process.platform === 'darwin') {
  shell = '/bin/bash';
  options = [path.join(root, 'install.sh'), ...args];
} else if (process.platform === 'win32') {
  shell = path.join(process.env.SystemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
  // Windows PowerShell must load its own modules when started from PowerShell 7.
  for (const key of Object.keys(env)) {
    if (key.toLowerCase() === 'psmodulepath') delete env[key];
  }
  options = ['-NoProfile', '-File', path.join(root, 'install.ps1')];
  if (args.includes('--install-only')) options.push('-InstallOnly');
  if (args.includes('--verbose')) options.push('-Verbose');
} else {
  console.error('This installer supports macOS and Windows.');
  process.exit(1);
}

// Inherit the terminal and project directory so Route can mask the key and launch Codex here.
const child = spawnSync(shell, options, { env, stdio: 'inherit' });
if (child.error) console.error(child.error.message);
process.exitCode = child.status ?? 1;
