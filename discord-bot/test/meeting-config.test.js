import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadConfig } from '../src/config.js';

const base = {
  DISCORD_TOKEN: 't', DISCORD_CLIENT_ID: 'c',
  DIRECTORY_BASE_URL: 'http://d', DIRECTORY_API_KEY: 'k',
  DOC_BASE_URL: 'http://o', DOC_API_KEY: 'k',
  LLM_BASE_URL: 'http://l', LLM_API_KEY: 'k',
  VERIFICATION_BASE_URL: 'http://v', VERIFICATION_API_KEY: 'k',
};

test('meeting config defaults apply when env is unset', () => {
  const cfg = loadConfig({ ...base });
  assert.equal(cfg.awsRegion, 'us-east-1');
  assert.equal(cfg.maxRecordingMs, 3_600_000);
  assert.equal(cfg.recordingSilenceMs, 1000);
});

test('meeting config reads overrides', () => {
  const cfg = loadConfig({ ...base, AWS_REGION: 'us-west-2', MAX_RECORDING_MS: '600000' });
  assert.equal(cfg.awsRegion, 'us-west-2');
  assert.equal(cfg.maxRecordingMs, 600000);
});
