import { test } from 'node:test';
import assert from 'node:assert/strict';
import { assembleTranscript, formatTimestamp } from '../src/meeting/transcript.js';

test('formatTimestamp renders mm:ss zero-padded', () => {
  assert.equal(formatTimestamp(0), '00:00');
  assert.equal(formatTimestamp(65_000), '01:05');
  assert.equal(formatTimestamp(600_000), '10:00');
});

test('assembleTranscript sorts by startMs and formats lines', () => {
  const segments = [
    { speaker: 'bob', startMs: 2000, text: "i'm great" },
    { speaker: 'alice', startMs: 0, text: 'hi how are you?' },
  ];
  assert.equal(
    assembleTranscript(segments),
    '[00:00] alice: hi how are you?\n[00:02] bob: i\'m great',
  );
});

test('assembleTranscript is stable for equal timestamps and trims empties', () => {
  const segments = [
    { speaker: 'a', startMs: 0, text: 'first' },
    { speaker: 'b', startMs: 0, text: 'second' },
    { speaker: 'c', startMs: 100, text: '   ' },
  ];
  assert.equal(assembleTranscript(segments), '[00:00] a: first\n[00:00] b: second');
});
