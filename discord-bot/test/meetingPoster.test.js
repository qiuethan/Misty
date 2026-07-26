import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeAttachmentPoster } from '../src/adapters/discord.js';

function fakeChannel({ sendImpl } = {}) {
  const calls = [];
  return {
    calls,
    send: sendImpl ?? (async (payload) => {
      calls.push(payload);
      return payload;
    }),
  };
}

test('poster posts a PDF attachment decoded from pdf_b64', async () => {
  const poster = makeAttachmentPoster();
  const pdfBytes = Buffer.from('%PDF-fake-content');
  const channel = fakeChannel();
  await poster({ channel, report: { pdf_b64: pdfBytes.toString('base64') } });

  assert.equal(channel.calls.length, 1);
  const { files } = channel.calls[0];
  assert.equal(files.length, 1);
  assert.equal(files[0].name, 'meeting-minutes.pdf');
  assert.ok(Buffer.from(files[0].attachment).equals(pdfBytes));
});

test('poster attaches audio as a second file when audio_b64 present', async () => {
  const poster = makeAttachmentPoster();
  const pdfBytes = Buffer.from('pdf-bytes');
  const audioBytes = Buffer.from('audio-bytes');
  const channel = fakeChannel();
  await poster({
    channel,
    report: { pdf_b64: pdfBytes.toString('base64'), audio_b64: audioBytes.toString('base64') },
  });

  const { files } = channel.calls[0];
  assert.equal(files.length, 2);
  assert.equal(files[0].name, 'meeting-minutes.pdf');
  assert.equal(files[1].name, 'meeting-audio.mp3');
  assert.ok(Buffer.from(files[1].attachment).equals(audioBytes));
});

test('poster falls back to PDF-only when the full send rejects, and never throws', async () => {
  const poster = makeAttachmentPoster();
  const pdfBytes = Buffer.from('pdf-bytes');
  const audioBytes = Buffer.from('audio-bytes');
  const calls = [];
  const channel = {
    send: async (payload) => {
      calls.push(payload);
      if (calls.length === 1) throw new Error('payload too large');
      return payload;
    },
  };

  await poster({
    channel,
    report: { pdf_b64: pdfBytes.toString('base64'), audio_b64: audioBytes.toString('base64') },
  });

  assert.equal(calls.length, 2);
  assert.equal(calls[0].files.length, 2);
  assert.equal(calls[1].files.length, 1);
  assert.equal(calls[1].files[0].name, 'meeting-minutes.pdf');
});

test('poster never throws even when every send rejects', async () => {
  const poster = makeAttachmentPoster();
  const channel = { send: async () => { throw new Error('down'); } };
  await assert.doesNotReject(() =>
    poster({ channel, report: { pdf_b64: Buffer.from('x').toString('base64') } }),
  );
});

test('poster never throws when the report is malformed (pdf_b64 missing)', async () => {
  const poster = makeAttachmentPoster();
  const channel = fakeChannel();
  await assert.doesNotReject(() => poster({ channel, report: {} }));
  // No send should have succeeded since attachment construction failed.
  assert.equal(channel.calls.length, 0);
});
