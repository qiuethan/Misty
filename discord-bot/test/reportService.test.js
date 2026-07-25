import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createMeetingReportService } from '../src/meeting/reportService.js';

test('buildReport assembles transcript, summarizes, and renders a pdf', async () => {
  const llm = { async chat() { return { content: '{"summary":"s","decisions":[],"actionItems":[]}' }; } };
  const svc = createMeetingReportService({ llmClient: llm });
  const meta = { title: 'T', startedAt: 'now', durationLabel: '1m', participants: ['a'] };
  const report = await svc.buildReport({
    segments: [{ speaker: 'a', startMs: 0, text: 'hello' }], meta,
  });
  assert.match(report.transcript, /a: hello/);
  assert.equal(report.minutes.summary, 's');
  assert.equal(report.pdfBuffer.subarray(0, 4).toString('latin1'), '%PDF');
});
