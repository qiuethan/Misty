import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderMeetingPdf } from '../src/meeting/pdf.js';

const meta = {
  title: 'Exec Sync', startedAt: '2026-07-25 18:00',
  durationLabel: '12m', participants: ['alice', 'bob'],
};
const minutes = { summary: 'We synced.', decisions: ['Ship it'], actionItems: ['alice: docs'] };

test('renderMeetingPdf returns a non-empty PDF buffer', async () => {
  const buf = await renderMeetingPdf({ minutes, transcript: '[00:00] alice: hi', meta });
  assert.ok(Buffer.isBuffer(buf));
  assert.ok(buf.length > 500);
  assert.equal(buf.subarray(0, 4).toString('latin1'), '%PDF');
});

test('renderMeetingPdf tolerates empty decisions/action items', async () => {
  const buf = await renderMeetingPdf({
    minutes: { summary: 's', decisions: [], actionItems: [] },
    transcript: 'x', meta,
  });
  assert.ok(buf.length > 500);
});
