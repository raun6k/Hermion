// Browser audio. Skeleton: play a WAV (TTS test clip). Mic capture (16 kHz PCM to the customer WS)
// and streamed TTS playback are built in the voice lane (docs/voice.md).

let ctx: AudioContext | null = null;

export async function playWavUrl(url: string): Promise<number> {
  ctx ??= new AudioContext();
  const res = await fetch(url);
  if (!res.ok) throw new Error(`audio fetch failed: ${res.status}`);
  const buffer = await ctx.decodeAudioData(await res.arrayBuffer());
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(ctx.destination);
  source.start();
  return buffer.duration;
}

export function startMicCapture(onPcmChunk: (chunk: ArrayBuffer) => void): never {
  void onPcmChunk;
  throw new Error("Mic capture is built in the voice lane (Stage 1, lane V)");
}
