import PDFDocument from 'pdfkit';

function bulletList(doc, items, emptyLabel) {
  if (!items.length) { doc.font('Helvetica-Oblique').fontSize(11).text(emptyLabel); return; }
  doc.font('Helvetica').fontSize(11);
  for (const item of items) doc.text(`• ${item}`);
}

function heading(doc, text) {
  doc.moveDown(0.8).font('Helvetica-Bold').fontSize(14).text(text).moveDown(0.3);
}

export function renderMeetingPdf({ minutes, transcript, meta }) {
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({ margin: 54 });
    const chunks = [];
    doc.on('data', (c) => chunks.push(c));
    doc.on('end', () => resolve(Buffer.concat(chunks)));
    doc.on('error', reject);

    doc.font('Helvetica-Bold').fontSize(20).text(meta.title);
    doc.font('Helvetica').fontSize(10).fillColor('#555')
      .text(`${meta.startedAt} · ${meta.durationLabel} · ${meta.participants.join(', ')}`)
      .fillColor('#000');

    heading(doc, 'Summary');
    doc.font('Helvetica').fontSize(11).text(minutes.summary || '(none)');
    heading(doc, 'Decisions');
    bulletList(doc, minutes.decisions, 'No decisions recorded.');
    heading(doc, 'Action Items');
    bulletList(doc, minutes.actionItems, 'No action items recorded.');
    heading(doc, 'Full Transcript');
    doc.font('Courier').fontSize(9).text(transcript || '(empty)');

    doc.end();
  });
}
