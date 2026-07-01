import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadConfig } from '../src/config.js';

const FULL = {
  DISCORD_TOKEN: 't',
  DISCORD_CLIENT_ID: 'c',
  DISCORD_GUILD_ID: 'g',
  DIRECTORY_BASE_URL: 'http://localhost:8000/',
  DIRECTORY_API_KEY: 'k',
};

test('loadConfig returns typed config and strips trailing slash', () => {
  const cfg = loadConfig(FULL);
  assert.equal(cfg.directoryBaseUrl, 'http://localhost:8000');
  assert.equal(cfg.discordToken, 't');
  assert.equal(cfg.directoryApiKey, 'k');
});

test('loadConfig throws listing missing vars', () => {
  assert.throws(() => loadConfig({ DISCORD_TOKEN: 't' }), /DIRECTORY_API_KEY/);
});
