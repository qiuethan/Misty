import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  startsWithBotMention,
  stripLeadingMention,
  threadHistoryToMessages,
  chunkForDiscord,
} from '../src/adapters/discord.js';

const BOT = '999';

test('startsWithBotMention: true only when the ping leads the message', () => {
  assert.equal(startsWithBotMention(`<@${BOT}> hello`, BOT), true);
  assert.equal(startsWithBotMention(`  <@!${BOT}> hi`, BOT), true); // nickname form + leading space
  assert.equal(startsWithBotMention(`hey <@${BOT}> covered this`, BOT), false); // mid-message
  assert.equal(startsWithBotMention('no mention', BOT), false);
  assert.equal(startsWithBotMention('', BOT), false);
});

test('stripLeadingMention removes the leading ping and following whitespace', () => {
  assert.equal(stripLeadingMention(`<@${BOT}>   how do I link?`, BOT), 'how do I link?');
  assert.equal(stripLeadingMention(`<@!${BOT}> hi`, BOT), 'hi');
  assert.equal(stripLeadingMention('no mention here', BOT), 'no mention here');
});

test('threadHistoryToMessages maps roles, collapses same-role, drops leading assistant', () => {
  const fetched = [
    { author: { id: BOT }, content: 'Hi! How can I help?' }, // leading assistant → dropped
    { author: { id: '1' }, content: `<@${BOT}> question one` }, // user (mention stripped)
    { author: { id: '2' }, content: 'and also this' }, // another human → same role, collapse
    { author: { id: BOT }, content: 'answer part 1' },
    { author: { id: BOT }, content: 'answer part 2' }, // collapse assistant
    { author: { id: '1' }, content: `<@${BOT}> follow up` },
  ];
  const msgs = threadHistoryToMessages(fetched, BOT);
  assert.deepEqual(msgs, [
    { role: 'user', content: 'question one\nand also this' },
    { role: 'assistant', content: 'answer part 1\nanswer part 2' },
    { role: 'user', content: 'follow up' },
  ]);
});

test('threadHistoryToMessages drops empty turns', () => {
  const fetched = [
    { author: { id: '1' }, content: `<@${BOT}>` }, // only a ping → empty after strip → dropped
    { author: { id: '1' }, content: 'real question' },
  ];
  assert.deepEqual(threadHistoryToMessages(fetched, BOT), [{ role: 'user', content: 'real question' }]);
});

test('chunkForDiscord splits on newline boundaries under 2000 chars', () => {
  assert.deepEqual(chunkForDiscord('short'), ['short']);
  assert.deepEqual(chunkForDiscord(''), []);
  const big = 'a'.repeat(1500) + '\n' + 'b'.repeat(1500);
  const chunks = chunkForDiscord(big);
  assert.equal(chunks.length, 2);
  assert.ok(chunks.every((c) => c.length <= 2000));
  assert.equal(chunks[0], 'a'.repeat(1500));
  assert.equal(chunks[1], 'b'.repeat(1500));
});

test('chunkForDiscord hard-splits a single oversized line', () => {
  const chunks = chunkForDiscord('x'.repeat(4500));
  assert.equal(chunks.length, 3);
  assert.ok(chunks.every((c) => c.length <= 2000));
  assert.equal(chunks.join(''), 'x'.repeat(4500));
});
