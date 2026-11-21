/**
 * Microphone capture for Voxtral: mono PCM16 little-endian at 16 kHz, about 100 ms per frame
 * (the /ws contract in INTEGRATION.md). Audio is only streamed while talking and never stored.
 */

const TARGET_RATE = 16000;
const FRAME_SAMPLES = 1600; // 100 ms at 16 kHz

// Runs on the audio thread: hands each block of raw samples back to the page.
const WORKLET = `
class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor('vybe-tap', Tap);
`;

export interface Mic {
  stop: () => void;
}

export class MicError extends Error {}

/** Starts recording; `onFrame` receives ArrayBuffers of PCM16 at 16 kHz. */
export async function startMic(onFrame: (frame: ArrayBuffer) => void): Promise<Mic> {
  if (!navigator.mediaDevices?.getUserMedia) throw new MicError('This browser can’t use the microphone.');
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch {
    throw new MicError('Microphone access was blocked. You can type instead.');
  }

  const ctx = new AudioContext();
  const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }));
  await ctx.audioWorklet.addModule(url);
  URL.revokeObjectURL(url);
  const source = ctx.createMediaStreamSource(stream);
  const tap = new AudioWorkletNode(ctx, 'vybe-tap');
  source.connect(tap);

  // Downsample by averaging (a simple low-pass) from the device rate to 16 kHz.
  const ratio = ctx.sampleRate / TARGET_RATE;
  let carry = 0; // fractional position into the next input block
  let pending: number[] = [];

  const flush = (all = false) => {
    while (pending.length >= FRAME_SAMPLES || (all && pending.length > 0)) {
      const chunk = pending.splice(0, FRAME_SAMPLES);
      const out = new Int16Array(chunk.length);
      for (let i = 0; i < chunk.length; i++) {
        const s = Math.max(-1, Math.min(1, chunk[i]));
        out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      onFrame(out.buffer);
    }
  };

  tap.port.onmessage = (e: MessageEvent<Float32Array>) => {
    const input = e.data;
    let pos = carry;
    while (pos + ratio <= input.length) {
      let sum = 0;
      const start = Math.floor(pos);
      const end = Math.floor(pos + ratio);
      for (let i = start; i < end; i++) sum += input[i];
      pending.push(sum / Math.max(1, end - start));
      pos += ratio;
    }
    carry = pos - input.length;
    flush();
  };

  let stopped = false;
  return {
    stop() {
      if (stopped) return;
      stopped = true;
      flush(true); // send the last partial frame so the end of the sentence isn't cut off
      tap.port.onmessage = null;
      source.disconnect();
      tap.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
      pending = [];
    },
  };
}
