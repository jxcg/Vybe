import { useEffect, useState } from 'react';
import type { BoardMsg } from '../contract';

const TICK_MS = 1000;

export interface Clock {
  /** the server's `now`, advanced locally since the last board (display only) */
  nowMs: number;
  /** this device's wall clock, for UI timings like "show Departed for 3 s" */
  wallMs: number;
}

export function useClock(board: BoardMsg | null, boardAt: number): Clock {
  const [wallMs, setWallMs] = useState(() => Date.now());

  useEffect(() => {
    const t = window.setInterval(() => setWallMs(Date.now()), TICK_MS);
    return () => window.clearInterval(t);
  }, []);

  // A fresh board resets the base; never let local time run behind the latest message.
  const wall = Math.max(wallMs, boardAt);
  const nowMs = board ? Date.parse(board.now) + (wall - boardAt) : wall;
  return { nowMs, wallMs: wall };
}
