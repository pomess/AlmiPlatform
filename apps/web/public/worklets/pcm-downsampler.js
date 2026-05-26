// AudioWorklet: downsample mic audio to 16 kHz mono Int16 PCM,
// batch into ~40 ms chunks, and post them to the main thread as
// ArrayBuffers ready to be sent over WebSocket.

const TARGET_RATE = 16000;
const CHUNK_MS = 40;

class PcmDownsampler extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.sourceRate = sampleRate; // global in worklet scope
    this.ratio = this.sourceRate / TARGET_RATE;
    this.samplesPerChunk = Math.round((TARGET_RATE * CHUNK_MS) / 1000);
    this.buffer = new Int16Array(this.samplesPerChunk);
    this.filled = 0;
    this.inputCursor = 0; // fractional read index into source
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel) return true;

    // Linear-interpolation downsample from sourceRate to 16 kHz.
    let i = this.inputCursor;
    while (i < channel.length) {
      const i0 = Math.floor(i);
      const i1 = Math.min(i0 + 1, channel.length - 1);
      const frac = i - i0;
      const sample = channel[i0] * (1 - frac) + channel[i1] * frac;
      // Clamp + float32 -> int16
      const clamped = Math.max(-1, Math.min(1, sample));
      this.buffer[this.filled++] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;

      if (this.filled >= this.samplesPerChunk) {
        // Copy into its own buffer because Int16Array shares the same
        // underlying memory across transfers if we reuse it.
        const out = new Int16Array(this.samplesPerChunk);
        out.set(this.buffer);
        this.port.postMessage(out.buffer, [out.buffer]);
        this.filled = 0;
      }

      i += this.ratio;
    }

    // Carry the fractional remainder into the next block so we keep phase.
    this.inputCursor = i - channel.length;
    if (this.inputCursor < 0) this.inputCursor = 0;
    return true;
  }
}

registerProcessor("pcm-downsampler", PcmDownsampler);
