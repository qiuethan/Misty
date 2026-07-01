import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderLinkResult, renderWhoami } from '../src/messages.js';

test('renderLinkResult covers every outcome', () => {
  assert.match(renderLinkResult({ outcome: 'LINKED', person: { display_name: 'Alex' } }), /Alex/);
  assert.match(renderLinkResult({ outcome: 'NOT_A_MEMBER' }), /exec/i);
  assert.match(renderLinkResult({ outcome: 'ALREADY_LINKED', detail: 'x' }), /already|couldn't|could not/i);
  assert.match(renderLinkResult({ outcome: 'DIRECTORY_DOWN' }), /unavailable|try again/i);
});

test('renderWhoami names the person', () => {
  assert.match(renderWhoami({ display_name: 'Alex' }), /Alex/);
});
