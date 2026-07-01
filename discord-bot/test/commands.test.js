import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as link from '../src/commands/link.js';
import * as whoami from '../src/commands/whoami.js';
import { commands } from '../src/commands/index.js';

function fakeInteraction({ email } = {}) {
  const replies = [];
  return {
    user: { id: '123', username: 'alex' },
    options: { getString: () => email },
    reply: async (payload) => { replies.push(payload); },
    replies,
  };
}

test('link is public and links via linkService', async () => {
  assert.equal(link.auth, 'public');
  const interaction = fakeInteraction({ email: 'alex@utmist.ca' });
  const ctx = {
    linkService: {
      linkByEmail: async (args) => {
        assert.equal(args.email, 'alex@utmist.ca');
        assert.equal(args.discordUserId, '123');
        assert.equal(args.discordHandle, 'alex');
        return { outcome: 'LINKED', person: { display_name: 'Alex' } };
      },
    },
  };
  await link.execute(interaction, ctx);
  assert.equal(interaction.replies[0].ephemeral, true);
  assert.match(interaction.replies[0].content, /Alex/);
});

test('whoami is linked-gated and renders the principal person', async () => {
  assert.equal(whoami.auth, 'linked');
  const interaction = fakeInteraction();
  await whoami.execute(interaction, { principal: { person: { display_name: 'Alex' } } });
  assert.match(interaction.replies[0].content, /Alex/);
  assert.equal(interaction.replies[0].ephemeral, true);
});

test('registry contains both commands keyed by name', () => {
  assert.equal(commands.get('link'), link);
  assert.equal(commands.get('whoami'), whoami);
});
