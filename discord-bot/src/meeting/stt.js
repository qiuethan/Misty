// Wraps @aws-sdk/client-transcribe-streaming. The `sdk` param is injected in
// tests; in production it is created lazily from the real package.

// AWS Transcribe streaming expects a series of small audio frames (~100 ms
// each), not one large event per caller-supplied buffer. 3200 bytes = 100 ms
// of 16 kHz mono s16le PCM (16000 samples/s * 2 bytes * 0.1 s = 3200 bytes).
const FRAME_BYTES = 3200;

export function createTranscribeClient({ region, sdk }) {
  async function resolveSdk() {
    if (sdk) return sdk;
    const mod = await import('@aws-sdk/client-transcribe-streaming');
    return {
      client: new mod.TranscribeStreamingClient({ region }),
      StartStreamTranscriptionCommand: mod.StartStreamTranscriptionCommand,
    };
  }

  return {
    async transcribePcm({ pcmChunks, sampleRate = 16000 }) {
      const { client, StartStreamTranscriptionCommand } = await resolveSdk();
      const audioStream = (async function* () {
        for await (const chunk of pcmChunks) {
          for (let off = 0; off < chunk.length; off += FRAME_BYTES) {
            yield { AudioEvent: { AudioChunk: chunk.subarray(off, off + FRAME_BYTES) } };
          }
        }
      })();
      const command = new StartStreamTranscriptionCommand({
        LanguageCode: 'en-US',
        MediaSampleRateHertz: sampleRate,
        MediaEncoding: 'pcm',
        AudioStream: audioStream,
      });
      const response = await client.send(command);
      const words = [];
      const finals = [];
      for await (const event of response.TranscriptResultStream) {
        const results = event?.TranscriptEvent?.Transcript?.Results ?? [];
        for (const r of results) {
          if (r.IsPartial) continue;
          const alt = r.Alternatives?.[0];
          if (!alt) continue;
          finals.push(alt.Transcript ?? '');
          for (const item of alt.Items ?? []) {
            if (item.Type === 'pronunciation' && typeof item.StartTime === 'number') {
              words.push({ text: item.Content, startMs: Math.round(item.StartTime * 1000) });
            }
          }
        }
      }
      return { text: finals.join(' ').trim(), words };
    },
  };
}
