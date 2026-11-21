import { useLayoutEffect, useRef } from 'react';
import { UserPlus } from 'lucide-react';
import type { BoardMsg } from '../contract';
import { dayWord, formatHM } from '../lib/time';
import { handoff } from '../lib/handoff';
import { ghost, MORPH_MS, prefersReducedMotion, shapeOf } from '../lib/morph';
import { RainMark } from './RainMark';
import { RollingNumber } from './RollingNumber';
import { ThemeToggle } from './ThemeToggle';
import { Wordmark } from './Wordmark';
import './BoardHeader.css';

interface Props {
  board: BoardMsg | null;
  nowMs: number;
}

function rainText(rainFrom: string | null, nowMs: number): string | null {
  if (!rainFrom) return null;
  return Date.parse(rainFrom) <= nowMs ? 'raining now' : `rain from ${formatHM(rainFrom)}`;
}

/** Size of the lavender dot the loading orb shrinks to before it becomes the count. */
const DOT_PX = 10;

export function BoardHeader({ board, nowMs }: Props) {
  const rain = board ? rainText(board.weather.rain_from, nowMs) : null;
  const countRef = useRef<HTMLSpanElement>(null);

  // Arriving from the loading screen: its orb folds down into the headline count.
  useLayoutEffect(() => {
    const orb = handoff.take('orb');
    const count = countRef.current;
    if (!orb || !count || prefersReducedMotion()) return;
    // Land on the digits themselves, not the middle of "10 things".
    const c = shapeOf(count.querySelector('.rn') ?? count);
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
    const start = { ...orb, bg: accent, border: 'transparent' };
    const end = {
      ...start,
      left: c.left + c.width / 2 - DOT_PX / 2,
      top: c.top + c.height / 2 - DOT_PX / 2,
      width: DOT_PX,
      height: DOT_PX,
    };
    void ghost(start, end, { opacity: [1, 0] });
    count.animate([{ opacity: 0, transform: 'scale(0.85)' }, { opacity: 1, transform: 'none' }], {
      duration: MORPH_MS * 0.6,
      delay: MORPH_MS * 0.45,
      easing: 'ease-out',
      fill: 'backwards',
    });
  }, []);

  return (
    <header className="board-header">
      <div className="board-header-bar">
        <Wordmark />
        <div className="board-header-actions">
          <ThemeToggle />
          <button className="icon-btn" type="button" aria-label="Invite friends">
            <UserPlus size={20} strokeWidth={2} />
          </button>
        </div>
      </div>
      {board && (
        <>
          <h1 className="t-title board-title">
            <span ref={countRef} className="board-title-count">
              <RollingNumber value={board.count} /> {board.count === 1 ? 'thing' : 'things'}
            </span>{' '}
            you can still make {dayWord(nowMs)}
          </h1>
          <p className="t-secondary board-sub">
            {rain && <RainMark />}
            <span>
              {board.area}
              {rain && `, ${rain}`}
            </span>
          </p>
        </>
      )}
    </header>
  );
}
