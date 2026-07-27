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

test('poster never attaches audio, even if the report still carries some', async () => {
  const poster = makeAttachmentPoster();
  const pdfBytes = Buffer.from('pdf-bytes');
  const channel = fakeChannel();
  await poster({
    channel,
    report: {
      pdf_b64: pdfBytes.toString('base64'),
      audio_b64: Buffer.from('audio-bytes').toString('base64'),
    },
  });

  const { files } = channel.calls[0];
  assert.equal(files.length, 1);
  assert.equal(files[0].name, 'meeting-minutes.pdf');
});

test('poster mentions the member who started the recording', async () => {
  const poster = makeAttachmentPoster();
  const channel = fakeChannel();
  await poster({
    channel,
    report: { pdf_b64: Buffer.from('pdf').toString('base64') },
    requesterId: '424242',
  });

  assert.equal(channel.calls.length, 1);
  assert.match(channel.calls[0].content, /<@424242>/);
});

test('poster posts without a mention when the requester is unknown', async () => {
  const poster = makeAttachmentPoster();
  const channel = fakeChannel();
  await poster({ channel, report: { pdf_b64: Buffer.from('pdf').toString('base64') } });

  assert.equal(channel.calls.length, 1);
  assert.doesNotMatch(channel.calls[0].content, /<@/);
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
