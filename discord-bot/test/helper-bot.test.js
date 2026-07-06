import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  startsWithBotMention,
  stripLeadingMention,
  threadHistoryToMessages,
  chunkForDiscord,
  handleMention,
} from '../src/adapters/discord.js';
import { DirectoryUnavailable } from '../src/directoryClient.js';

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

const BOT_ID = '999';

// Fake channel/thread: records sent messages + typing; can be a thread or not.
function fakeChannel({ isThread = false, history = [] } = {}) {
  const sent = [];
  return {
    sent,
    typing: 0,
    isThread: () => isThread,
    async send(content) { sent.push(content); },
    async sendTyping() { this.typing += 1; },
    messages: { fetch: async () => ({ values: () => history }) },
  };
}

function fakeMessage({ content, authorId = '1', channel, thread }) {
  return {
    content,
    author: { id: authorId, bot: false },
    channel,
    reply: async (c) => { (channel.replies ??= []).push(c); },
    startThread: async () => thread,
  };
}

function ctx({ principal = { person: { id: 'p1', display_name: 'Alex' } }, answer, dirThrows = false } = {}) {
  return {
    directory: {
      getPersonByDiscordId: async () => (dirThrows ? (() => { throw new DirectoryUnavailable('down'); })() : principal?.person ?? null),
    },
    helperService: { answer: answer ?? (async () => ({ content: 'the answer' })) },
  };
}

test('handleMention in a channel: opens a thread and posts the answer', async () => {
  const thread = fakeChannel({ isThread: true });
  const channel = fakeChannel({ isThread: false });
  const message = fakeMessage({ content: `<@${BOT_ID}> how do I link?`, channel, thread });
  await handleMention(message, { appContext: ctx(), botId: BOT_ID });
  assert.deepEqual(thread.sent, ['the answer']);
  assert.equal(thread.typing, 1);
});

test('handleMention in a thread: replays history and posts in the thread', async () => {
  let seen;
  const answer = async ({ messages }) => { seen = messages; return { content: 'reply' }; };
  const history = [
    { author: { id: BOT_ID }, content: 'earlier answer' },
    { author: { id: '1' }, content: `<@${BOT_ID}> follow up` },
  ];
  const thread = fakeChannel({ isThread: true, history });
  const message = fakeMessage({ content: `<@${BOT_ID}> follow up`, channel: thread });
  await handleMention(message, { appContext: ctx({ answer }), botId: BOT_ID });
  assert.deepEqual(thread.sent, ['reply']);
  assert.deepEqual(seen, [{ role: 'assistant', content: 'earlier answer' }, { role: 'user', content: 'follow up' }].filter((m) => m.role === 'user'));
});

test('handleMention: unlinked author gets the link prompt, no thread', async () => {
  const channel = fakeChannel({ isThread: false });
  const message = fakeMessage({ content: `<@${BOT_ID}> hi`, channel });
  await handleMention(message, { appContext: ctx({ principal: null }), botId: BOT_ID });
  assert.equal(channel.replies.length, 1);
  assert.match(channel.replies[0], /link/i);
});

test('handleMention: LlmUnavailable posts a friendly error, no throw', async () => {
  const thread = fakeChannel({ isThread: true });
  const channel = fakeChannel({ isThread: false });
  const message = fakeMessage({ content: `<@${BOT_ID}> hi`, channel, thread });
  const answer = async () => { throw new Error('llm down'); };
  await handleMention(message, { appContext: ctx({ answer }), botId: BOT_ID });
  assert.equal(thread.sent.length, 1);
  assert.match(thread.sent[0], /trouble/i);
});

test('handleMention: a bare ping with no question does nothing', async () => {
  const channel = fakeChannel({ isThread: false });
  const message = fakeMessage({ content: `<@${BOT_ID}>`, channel });
  await handleMention(message, { appContext: ctx(), botId: BOT_ID });
  assert.equal(channel.replies, undefined);
});
