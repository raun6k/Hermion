// Browser audio (docs/voice.md): mic -> 16 kHz PCM chunks for the customer WS, and streamed TTS playback
// (raw 16-bit mono PCM at 24 kHz) that can be stopped instantly on barge-in (`tts_stop`).

export const TTS_SAMPLE_RATE = 24_000;

let ctx: AudioContext | null = null;

function audioContext(): AudioContext {
  ctx ??= new AudioContext();
  return ctx;
}

export async function playWavUrl(url: string): Promise<number> {
  const c = audioContext();
  const res = await fetch(url);
  if (!res.ok) throw new Error(`audio fetch failed: ${res.status}`);
  const buffer = await c.decodeAudioData(await res.arrayBuffer());
  const source = c.createBufferSource();
  source.buffer = buffer;
  source.connect(c.destination);
  source.start();
  return buffer.duration;
}

export interface MicCapture {
  /** Stop sending audio (mute). The mic stays open so unmute is instant. */
  setMuted: (muted: boolean) => void;
  stop: () => void;
}

/** Open the mic and call `onPcmChunk` with 100 ms of 16 kHz mono 16-bit PCM while not muted. */
export async function startMicCapture(onPcmChunk: (chunk: ArrayBuffer) => void): Promise<MicCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const c = new AudioContext();
  await c.audioWorklet.addModule("/pcm-capture-worklet.js");
  const source = c.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(c, "pcm-capture");
  let muted = false;
  node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
    if (!muted) onPcmChunk(e.data);
  };
  source.connect(node); // the worklet has no output: nothing is played back
  return {
    setMuted: (m) => {
      muted = m;
    },
    stop: () => {
      node.port.onmessage = null;
      source.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      void c.close();
    },
  };
}

/** Plays raw PCM chunks back to back as they arrive; `stop()` silences everything queued. */
export class TtsPlayer {
  private nextStart = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private carry: Uint8Array | null = null;
  private abort: AbortController | null = null;
  onEnded?: () => void;

  /** Queue one chunk of 16-bit little-endian mono PCM at TTS_SAMPLE_RATE. */
  enqueue(chunk: ArrayBuffer): void {
    let bytes = new Uint8Array(chunk);
    if (this.carry) {
      const joined = new Uint8Array(this.carry.length + bytes.length);
      joined.set(this.carry);
      joined.set(bytes, this.carry.length);
      bytes = joined;
      this.carry = null;
    }
    if (bytes.length % 2) {
      this.carry = bytes.slice(bytes.length - 1);
      bytes = bytes.slice(0, bytes.length - 1);
    }
    if (!bytes.length) return;
    const c = audioContext();
    void c.resume();
    const pcm = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.length / 2);
    const buffer = c.createBuffer(1, pcm.length, TTS_SAMPLE_RATE);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 0x8000;
    const source = c.createBufferSource();
    source.buffer = buffer;
    source.connect(c.destination);
    const startAt = Math.max(c.currentTime + 0.02, this.nextStart);
    source.start(startAt);
    this.nextStart = startAt + buffer.duration;
    this.sources.add(source);
    source.onended = () => {
      this.sources.delete(source);
      if (!this.sources.size && !this.carry) this.onEnded?.();
    };
  }

  /** Barge-in: drop queued audio now. */
  stop(): void {
    this.abort?.abort();
    this.abort = null;
    for (const s of this.sources) {
      s.onended = null;
      try {
        s.stop();
      } catch {
        // already finished
      }
    }
    this.sources.clear();
    this.carry = null;
    this.nextStart = 0;
  }

  get playing(): boolean {
    return this.sources.size > 0;
  }

  /** Fetch a streamed PCM response (dev page) and play it as it arrives. */
  async playStream(url: string): Promise<void> {
    this.stop();
    this.abort = new AbortController();
    const res = await fetch(url, { signal: this.abort.signal });
    if (!res.ok || !res.body) throw new Error(`tts stream failed: ${res.status}`);
    const reader = res.body.getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      this.enqueue(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength) as ArrayBuffer);
    }
  }
}
