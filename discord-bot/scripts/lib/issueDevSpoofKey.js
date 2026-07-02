import { spawn } from 'node:child_process';

export function parseCliKeyOutput(stdout) {
  const line = stdout.trim().split(/\r?\n/).find((l) => l.trim().startsWith('tt_'));
  if (!line) throw new Error('no key found in team-tracking-keys output');
  return line.trim();
}

export function issueDevSpoofKey({ teamTrackingDir, databaseUrl, name }) {
  return new Promise((resolve, reject) => {
    const args = [
      'run', 'team-tracking-keys', 'issue',
      '--name', name,
      '--scopes',
      'people:read', 'people:write', 'identifiers:read', 'identifiers:write', 'dev:spoof',
    ];
    const child = spawn('uv', args, {
      cwd: teamTrackingDir,
      env: { ...process.env, DATABASE_URL: databaseUrl },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '', stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('exit', (code) => {
      if (code !== 0) return reject(new Error(`team-tracking-keys exited ${code}: ${stderr}`));
      try {
        resolve(parseCliKeyOutput(stdout));
      } catch (e) {
        reject(e);
      }
    });
  });
}
