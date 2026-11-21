import { useCallback, useEffect, useState } from 'react';

export interface PresenceEntry {
  key: string;
  leaving: boolean;
  /** enter-animation delay, staggered across keys that appeared together */
  delay: number;
}

function reconcile(prev: PresenceEntry[], keys: string[], stagger: number): PresenceEntry[] {
  let changed = false;
  const next = prev.map((e) => {
    const leaving = !keys.includes(e.key);
    if (leaving === e.leaving) return e;
    changed = true;
    return { ...e, leaving, delay: 0 };
  });
  let added = 0;
  for (const key of keys) {
    if (prev.some((e) => e.key === key)) continue;
    changed = true;
    next.push({ key, leaving: false, delay: added++ * stagger });
  }
  return changed ? next : prev;
}

/** Keeps removed keys mounted (flagged `leaving`) until `exited(key)` is called after their exit animation. */
export function usePresence(keys: string[], stagger = 60) {
  const [entries, setEntries] = useState<PresenceEntry[]>(() =>
    keys.map((key, i) => ({ key, leaving: false, delay: i * stagger })),
  );
  const signature = keys.join('\n');

  useEffect(() => {
    setEntries((prev) => reconcile(prev, signature ? signature.split('\n') : [], stagger));
  }, [signature, stagger]);

  const exited = useCallback((key: string) => {
    setEntries((prev) => prev.filter((e) => !(e.key === key && e.leaving)));
  }, []);

  return { entries, exited };
}
