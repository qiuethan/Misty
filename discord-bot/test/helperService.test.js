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
    listTeams: async () => [
      { id: 't1', label: 'Events' },
      { id: 't2', label: 'Web' },
    ],
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

test('answer resolves team labels with ONE listTeams call, not N getTeam calls', async () => {
  const capture = {};
  const calls = { listTeams: 0, getTeam: 0 };
  const directory = {
    listMemberships: async () => [{ team_id: 't1' }, { team_id: 't2' }, { team_id: 't3' }],
    listTeams: async ({ activeOnly }) => {
      calls.listTeams += 1;
      assert.equal(activeOnly, true);
      return [
        { id: 't1', label: 'Events' },
        { id: 't2', label: 'Web' },
        { id: 't3', label: 'ML' },
      ];
    },
    getTeam: async () => { calls.getTeam += 1; return null; },
  };
  const svc = createHelperService({ llmClient: fakeLlm(capture), directory });
  await svc.answer({ messages: MESSAGES, principal: PRINCIPAL });
  assert.equal(calls.listTeams, 1, 'exactly one listTeams round-trip');
  assert.equal(calls.getTeam, 0, 'no per-membership getTeam round-trips');
  // Labels preserve membership order.
  assert.match(capture.args.system, /on Events, Web, ML/);
});

test('answer drops team_ids absent from the active team list (getTeam-404 parity)', async () => {
  const capture = {};
  const directory = {
    listMemberships: async () => [{ team_id: 't1' }, { team_id: 'gone' }, { team_id: 't2' }],
    // 'gone' is not in the active list — mirrors getTeam returning null on 404.
    listTeams: async () => [
      { id: 't1', label: 'Events' },
      { id: 't2', label: 'Web' },
    ],
  };
  const svc = createHelperService({ llmClient: fakeLlm(capture), directory });
  await svc.answer({ messages: MESSAGES, principal: PRINCIPAL });
  assert.match(capture.args.system, /on Events, Web\./);
  assert.doesNotMatch(capture.args.system, /gone/);
});

test('answer omits the team clause when there are no memberships', async () => {
  const capture = {};
  const directory = { listMemberships: async () => [], listTeams: async () => [] };
  const svc = createHelperService({ llmClient: fakeLlm(capture), directory });
  await svc.answer({ messages: MESSAGES, principal: PRINCIPAL });
  assert.match(capture.args.system, /Alex/);
  assert.doesNotMatch(capture.args.system, /who is on/);
});

test('answer falls back to name-only when the directory throws', async () => {
  const capture = {};
  const directory = { listMemberships: async () => { throw new Error('dir down'); }, listTeams: async () => [] };
  const svc = createHelperService({ llmClient: fakeLlm(capture), directory });
  const res = await svc.answer({ messages: MESSAGES, principal: PRINCIPAL });
  assert.deepEqual(res, { content: 'answer' });
  assert.match(capture.args.system, /Alex/);
  assert.doesNotMatch(capture.args.system, /who is on/);
});

test('answer propagates LlmUnavailable from the client', async () => {
  const capture = {};
  const directory = { listMemberships: async () => [], listTeams: async () => [] };
  const svc = createHelperService({ llmClient: fakeLlm(capture, { throws: true }), directory });
  await assert.rejects(() => svc.answer({ messages: MESSAGES, principal: PRINCIPAL }), LlmUnavailable);
});
