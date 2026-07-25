import { assembleTranscript } from './transcript.js';
import { summarizeMinutes } from './minutes.js';
import { renderMeetingPdf } from './pdf.js';

export function createMeetingReportService({ llmClient, model }) {
  return {
    async buildReport({ segments, meta }) {
      const transcript = assembleTranscript(segments);
      const minutes = await summarizeMinutes({ transcript, llmClient, model });
      const pdfBuffer = await renderMeetingPdf({ minutes, transcript, meta });
      return { transcript, minutes, pdfBuffer };
    },
  };
}
