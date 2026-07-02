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

const commands = new Map([[linkCmd.name, linkCmd]]);
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
});
