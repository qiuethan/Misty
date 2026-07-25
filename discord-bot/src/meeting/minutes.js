export const MINUTES_SYSTEM_PROMPT =
  'You write concise meeting minutes for a student organization. ' +
  'Given a timestamped transcript, respond with ONLY a JSON object of the shape ' +
  '{"summary": string, "decisions": string[], "actionItems": string[]}. ' +
  'summary is 2-5 sentences. decisions are concrete choices the group made. ' +
  'actionItems are follow-ups, each prefixed with the owner when known. No prose outside the JSON.';

function extractJson(text) {
  const trimmed = (text ?? '').trim();
  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidate = fenced ? fenced[1].trim() : trimmed;
  const start = candidate.indexOf('{');
  const end = candidate.lastIndexOf('}');
  if (start === -1 || end === -1 || end < start) return null;
  try {
    return JSON.parse(candidate.slice(start, end + 1));
  } catch {
    return null;
  }
}

export async function summarizeMinutes({ transcript, llmClient, model }) {
  const { content } = await llmClient.chat({
    system: MINUTES_SYSTEM_PROMPT,
    model,
    maxTokens: 1500,
    messages: [{ role: 'user', content: `Transcript:\n\n${transcript}` }],
  });
  const parsed = extractJson(content);
  if (!parsed || typeof parsed.summary !== 'string') {
    return { summary: (content ?? '').trim(), decisions: [], actionItems: [] };
  }
  return {
    summary: parsed.summary,
    decisions: Array.isArray(parsed.decisions) ? parsed.decisions.map(String) : [],
    actionItems: Array.isArray(parsed.actionItems) ? parsed.actionItems.map(String) : [],
  };
}
