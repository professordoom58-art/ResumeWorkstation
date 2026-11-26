const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const PORT = process.env.CDP_PORT || '9223';
const PROFILE = path.join(__dirname, 'profile-' + PORT);
fs.mkdirSync(PROFILE, { recursive: true });

const p = spawn(CHROME, [
  '--remote-debugging-port=' + PORT,
  '--user-data-dir=' + PROFILE,
  '--no-first-run', '--no-default-browser-check',
  '--disable-blink-features=AutomationControlled',
  '--window-size=1440,950',
  'about:blank',
], { detached: true, stdio: 'ignore' });
p.on('error', e => console.log('spawn error:', e.message));
p.unref();
console.log('chrome pid', p.pid, 'port', PORT);
