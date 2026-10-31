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

const rms = (pcm: Int16Array): number => {
  let sum = 0;
  for (const v of pcm) sum += v * v;
  return Math.sqrt(sum / Math.max(pcm.length, 1));
};

/**
 * Keeps background noise from looking like speech (docs/voice.md#turn-taking). The noise floor is the
 * quietest level of the last ~3 s, updated from quiet frames only. Two 100 ms chunks must clear the absolute
 * level and margin above that floor; up to 200 ms of pre-roll is released with them to keep soft starts.
 * A 300 ms hangover bridges brief dips and pauses. Everything else is sent as silence, because the STT
 * stream must keep flowing. There is no startup calibration period that drops the first frames.
 */
export class NoiseGate {
  private levels: number[] = [];
  private run: ArrayBuffer[] = [];
  private preRoll: ArrayBuffer[] = [];
  private speaking = false;
  private quiet = 0;
  constructor(
    private readonly windowChunks = 30,
    private readonly minChunks = 2,
    private readonly margin = 2,
    private readonly hangoverChunks = 3,
    private readonly preRollChunks = 2,
  ) {}

  /** Estimated room floor (exposed for tests and debugging). */
  get floor(): number {
    return this.levels.length ? Math.min(...this.levels) : 0;
  }

  process(chunk: ArrayBuffer): ArrayBuffer {
    const level = rms(new Int16Array(chunk));
    const loud = level > Math.max(this.floor * this.margin, 350);
    if (loud) {
      this.quiet = 0;
      if (this.speaking) return chunk;
      this.run.push(chunk);
      if (this.run.length < this.minChunks) return new ArrayBuffer(chunk.byteLength);
      this.speaking = true;
      const released = concat([...this.preRoll, ...this.run]);
      this.preRoll = [];
      this.run = [];
      return released;
    }

    if (this.speaking && this.quiet < this.hangoverChunks) {
      this.quiet++;
      return chunk; // keep short dips and pauses inside speech
    }
    this.speaking = false;
    this.quiet = 0;
    this.rememberFloor(level); // speech never raises the room estimate
    for (const buffered of this.run) this.rememberPreRoll(buffered);
    this.run = [];
    this.rememberPreRoll(chunk);
    return new ArrayBuffer(chunk.byteLength);
  }

  private rememberFloor(level: number): void {
    this.levels.push(level);
    if (this.levels.length > this.windowChunks) this.levels.shift();
  }

  private rememberPreRoll(chunk: ArrayBuffer): void {
    this.preRoll.push(chunk);
    if (this.preRoll.length > this.preRollChunks) this.preRoll.shift();
  }
}

function concat(chunks: ArrayBuffer[]): ArrayBuffer {
  const out = new Uint8Array(chunks.reduce((n, c) => n + c.byteLength, 0));
  let at = 0;
  for (const c of chunks) {
    out.set(new Uint8Array(c), at);
    at += c.byteLength;
  }
  return out.buffer;
}

/** Open the mic and call `onPcmChunk` with 100 ms of 16 kHz mono 16-bit PCM while not muted. */
export async function startMicCapture(onPcmChunk: (chunk: ArrayBuffer) => void): Promise<MicCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: false },
  });
  const c = new AudioContext();
  await c.resume();
  await c.audioWorklet.addModule("/pcm-capture-worklet.js");
  const source = c.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(c, "pcm-capture");
  let muted = false;
  const gate = new NoiseGate();
  node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
    if (!muted) onPcmChunk(gate.process(e.data));
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

  /** Unlock audio playback from a customer gesture. */
  unlock(): void {
    void audioContext().resume();
  }

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
