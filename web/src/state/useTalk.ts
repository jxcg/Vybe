import { useCallback, useEffect, useRef } from 'react';
import type { TalkPurpose } from '../contract';
import { MicError, startMic, type Mic } from '../lib/mic';
import { useStore } from './store';

/**
 * Voice talking to the server: talk_start → mic PCM frames → talk_end. Voxtral turns the audio
 * into chips. Nothing is recorded or saved on the device.
 */
export function useTalk(purpose: TalkPurpose, onDenied?: () => void) {
  const { send, sendAudio, dispatch } = useStore();
  const mic = useRef<Mic | null>(null);
  const starting = useRef<Promise<void> | null>(null);

  const note = useCallback(
    (text: string) => dispatch({ type: 'server', msg: { type: 'note', text }, at: Date.now() }),
    [dispatch],
  );

  const start = useCallback(() => {
    send({ type: 'talk_start', purpose });
    starting.current = startMic(sendAudio)
      .then((m) => {
        mic.current = m;
      })
      .catch((e: unknown) => {
        send({ type: 'talk_end' }); // the server answers with empty chips, so the UI doesn't hang
        note(e instanceof MicError ? e.message : 'The microphone didn’t start. You can type instead.');
        onDenied?.();
      });
  }, [send, sendAudio, purpose, note, onDenied]);

  const stop = useCallback(() => {
    // Wait for the mic to finish starting (a very quick tap), then send the last audio and end.
    const pending = starting.current ?? Promise.resolve();
    void pending.then(() => {
      if (!mic.current) return;
      mic.current.stop();
      mic.current = null;
      send({ type: 'talk_end' });
    });
  }, [send]);

  useEffect(() => () => mic.current?.stop(), []);
  return { start, stop };
}
