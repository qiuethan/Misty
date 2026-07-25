import { test } from 'node:test';
import assert from 'node:assert/strict';
import { summarizeMinutes } from '../src/meeting/minutes.js';

function fakeLlm(content) {
  return { calls: [], async chat(args) { this.calls.push(args); return { content }; } };
}

test('summarizeMinutes parses structured JSON from the model', async () => {
  const llm = fakeLlm(JSON.stringify({
    summary: 'Discussed the launch.',
    decisions: ['Ship Friday'],
    actionItems: ['alice: write changelog'],
  }));
  const out = await summarizeMinutes({ transcript: '[00:00] alice: hi', llmClient: llm });
  assert.equal(out.summary, 'Discussed the launch.');
  assert.deepEqual(out.decisions, ['Ship Friday']);
  assert.deepEqual(out.actionItems, ['alice: write changelog']);
  // transcript is passed in the user message
  assert.match(llm.calls[0].messages.at(-1).content, /alice: hi/);
});

test('summarizeMinutes tolerates code-fenced JSON', async () => {
  const llm = fakeLlm('```json\n{"summary":"s","decisions":[],"actionItems":[]}\n```');
  const out = await summarizeMinutes({ transcript: 'x', llmClient: llm });
  assert.equal(out.summary, 's');
});

test('summarizeMinutes falls back to raw text on unparseable output', async () => {
  const llm = fakeLlm('not json at all');
  const out = await summarizeMinutes({ transcript: 'x', llmClient: llm });
  assert.equal(out.summary, 'not json at all');
  assert.deepEqual(out.decisions, []);
  assert.deepEqual(out.actionItems, []);
});
