// AudioWorklet: mic samples -> 16 kHz mono 16-bit PCM chunks (100 ms) posted to the main thread.
// Resamples from the context rate (usually 44.1/48 kHz) with a simple averaging low-pass.
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.pos = 0;
    this.out = [];
    this.chunk = 1600;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input) return true;
    for (let i = 0; i < input.length; i++) {
      this.pos += 1;
      this.acc = (this.acc || 0) + input[i];
      this.n = (this.n || 0) + 1;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        const s = Math.max(-1, Math.min(1, this.acc / this.n));
        this.out.push(s < 0 ? s * 0x8000 : s * 0x7fff);
        this.acc = 0;
        this.n = 0;
        if (this.out.length >= this.chunk) {
          this.port.postMessage(new Int16Array(this.out.splice(0, this.chunk)).buffer);
        }
      }
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCapture);
