import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { buildServer } from '../src/web/server.js';
import { defineCommand } from '../src/defineCommand.js';

const linkCmd = defineCommand({
  name: 'link',
  description: 'link',
  auth: 'public',
  options: [{ name: 'email', type: 'string', required: true, description: 'e' }],
  handler: async ({ options, discordUserId }) => ({
    content: `linked ${options.email} as ${discordUserId}`,
    ephemeral: true,
  }),
});

const echoCmd = defineCommand({
  name: 'echo',
  description: 'echo options back',
  auth: 'public',
  options: [
    { name: 'user', type: 'user', required: true, description: 'a user' },
    { name: 'active_only', type: 'boolean', required: false, description: 'flag' },
  ],
  handler: async ({ options }) => ({
    content: JSON.stringify(options),
  }),
});

const commands = new Map([[linkCmd.name, linkCmd], [echoCmd.name, echoCmd]]);
const appContext = { directory: {} };

describe('web server', () => {
  let server;
  before(async () => {
    server = await buildServer({ commands, appContext });
    await server.ready();
  });
  after(async () => {
    await server.close();
  });

  test('GET /api/commands returns registry shape', async () => {
    const resp = await server.inject({ method: 'GET', url: '/api/commands' });
    assert.equal(resp.statusCode, 200);
    const body = resp.json();
    assert.equal(body[0].name, 'link');
    assert.equal(body[0].options[0].name, 'email');
    assert.equal(body[0].subcommands.length, 0);
  });

  test('POST /api/commands/:name/run returns the ReplyPayload', async () => {
    const resp = await server.inject({
      method: 'POST',
      url: '/api/commands/link/run',
      payload: { options: { email: 'x@y' }, actingAs: '999' },
    });
    assert.equal(resp.statusCode, 200);
    const body = resp.json();
    assert.ok(body.content.includes('x@y'));
    assert.ok(body.content.includes('999'));
  });

  test('POST /api/commands/:name/run: unknown command → 404', async () => {
    const resp = await server.inject({
      method: 'POST',
      url: '/api/commands/nope/run',
      payload: { options: {}, actingAs: '1' },
    });
    assert.equal(resp.statusCode, 404);
  });

  test('POST /api/commands/:name/run coerces `user` option string into { id }', async () => {
    const resp = await server.inject({
      method: 'POST',
      url: '/api/commands/echo/run',
      payload: {
        options: { user: '123456789012345678', active_only: 'false' },
        actingAs: '999',
      },
    });
    assert.equal(resp.statusCode, 200);
    const body = JSON.parse(resp.json().content);
    assert.deepEqual(body.user, { id: '123456789012345678' });
  });

  test('POST /api/commands/:name/run coerces `boolean` option string "false" into false', async () => {
    const resp = await server.inject({
      method: 'POST',
      url: '/api/commands/echo/run',
      payload: {
        options: { user: '1', active_only: 'false' },
        actingAs: '999',
      },
    });
    assert.equal(resp.statusCode, 200);
    const body = JSON.parse(resp.json().content);
    assert.equal(body.active_only, false);
  });

  test('POST /api/commands/:name/run without actingAs → 400', async () => {
    const resp = await server.inject({
      method: 'POST',
      url: '/api/commands/link/run',
      payload: { options: { email: 'x@y' } },
    });
    assert.equal(resp.statusCode, 400);
    assert.equal(resp.json().error, 'actingAs is required');
  });

  test('POST /api/commands/:name/run with whitespace-only actingAs → 400', async () => {
    const resp = await server.inject({
      method: 'POST',
      url: '/api/commands/link/run',
      payload: { options: { email: 'x@y' }, actingAs: '   ' },
    });
    assert.equal(resp.statusCode, 400);
    assert.equal(resp.json().error, 'actingAs is required');
  });
});
