import { test } from 'node:test';
import assert from 'node:assert/strict';
import { hydrateMentions } from '../src/web/public/mentions.js';

const peopleMap = new Map([
  ['111', 'Alex'],
  ['222', 'Bea'],
]);

test('hydrateMentions swaps a known <@id> for a styled pill', () => {
  const html = hydrateMentions('Welcome <@111>!', peopleMap);
  assert.ok(html.includes('<span class="mention">@Alex</span>'));
  assert.ok(!html.includes('<@111>'));
});

test('hydrateMentions renders unknown ids with (unknown) marker', () => {
  const html = hydrateMentions('Hi <@999>', peopleMap);
  assert.ok(html.includes('&lt;@999 (unknown)&gt;') || html.includes('<@999 (unknown)>'));
});

test('hydrateMentions escapes surrounding HTML', () => {
  const html = hydrateMentions('<b>Alex</b> <@111>', peopleMap);
  assert.ok(html.includes('&lt;b&gt;Alex&lt;/b&gt;'));
  assert.ok(html.includes('<span class="mention">@Alex</span>'));
});

test('hydrateMentions handles multiple mentions', () => {
  const html = hydrateMentions('<@111> and <@222>', peopleMap);
  assert.ok(html.includes('@Alex'));
  assert.ok(html.includes('@Bea'));
});

test('hydrateMentions leaves text without mentions unchanged (escaped)', () => {
  const html = hydrateMentions('plain text', peopleMap);
  assert.equal(html, 'plain text');
});
