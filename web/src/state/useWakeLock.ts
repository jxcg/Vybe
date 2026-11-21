import { useEffect } from 'react';

/** Keeps the screen on while mounted (the board is a live display). Silently no-ops if unsupported. */
export function useWakeLock(): void {
  useEffect(() => {
    if (!('wakeLock' in navigator)) return;
    let sentinel: WakeLockSentinel | null = null;
    let active = true;

    const acquire = async () => {
      if (document.visibilityState !== 'visible' || sentinel) return;
      try {
        const s = await navigator.wakeLock.request('screen');
        if (!active) {
          void s.release();
          return;
        }
        sentinel = s;
        s.addEventListener('release', () => {
          sentinel = null;
        });
      } catch {
        // Battery saver or permissions policy: the board still works.
      }
    };

    void acquire();
    document.addEventListener('visibilitychange', acquire);
    return () => {
      active = false;
      document.removeEventListener('visibilitychange', acquire);
      void sentinel?.release();
    };
  }, []);
}
