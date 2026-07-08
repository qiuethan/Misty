import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHelperService } from '../src/helperService.js';
import { LlmUnavailable } from '../src/llmClient.js';

function fakeLlm(capture, { throws = false } = {}) {
  return {
    async chat(args) {
      capture.args = args;
      if (throws) throw new LlmUnavailable('down');
      return { content: 'answer', model: 'claude-sonnet-4-6', usage: {} };
    },
  };
}

const PRINCIPAL = { person: { id: 'p1', display_name: 'Alex' } };
const MESSAGES = [{ role: 'user', content: 'how do I link?' }];

test('answer builds a system prompt with name + teams and passes messages through', async () => {
  const capture = {};
  const directory = {
    listMemberships: async ({ personId, activeOnly }) => {
      assert.equal(personId, 'p1');
      assert.equal(activeOnly, true);
      return [{ team_id: 't1' }, { team_id: 't2' }];
    },
    getTeam: async (id) => ({ t1: { label: 'Events' }, t2: { label: 'Web' } })[id],
  };
  const svc = createHelperService({ llmClient: fakeLlm(capture), directory });
  const res = await svc.answer({ messages: MESSAGES, principal: PRINCIPAL });

  assert.deepEqual(res, { content: 'answer' });
  assert.deepEqual(capture.args.messages, MESSAGES);
  assert.equal(capture.args.maxTokens, 1024);
  assert.equal('model' in capture.args, false);
  assert.match(capture.args.system, /Alex/);
  assert.match(capture.args.system, /Events/);
  assert.match(capture.args.system, /Web/);
});

test('answer omits the team clause when there are no memberships', async () => {
  const capture = {};
  const directory = { listMemberships: async () => [], getTeam: async () => null };
  const svc = createHelperService({ llmClient: fakeLlm(capture), directory });
  await svc.answer({ messages: MESSAGES, principal: PRINCIPAL });
  assert.match(capture.args.system, /Alex/);
  assert.doesNotMatch(capture.args.system, /who is on/);
});

test('answer falls back to name-only when the directory throws', async () => {
  const capture = {};
  const directory = { listMemberships: async () => { throw new Error('dir down'); }, getTeam: async () => null };
  const svc = createHelperService({ llmClient: fakeLlm(capture), directory });
  const res = await svc.answer({ messages: MESSAGES, principal: PRINCIPAL });
  assert.deepEqual(res, { content: 'answer' });
  assert.match(capture.args.system, /Alex/);
  assert.doesNotMatch(capture.args.system, /who is on/);
});

test('answer propagates LlmUnavailable from the client', async () => {
  const capture = {};
  const directory = { listMemberships: async () => [], getTeam: async () => null };
  const svc = createHelperService({ llmClient: fakeLlm(capture, { throws: true }), directory });
  await assert.rejects(() => svc.answer({ messages: MESSAGES, principal: PRINCIPAL }), LlmUnavailable);
});
