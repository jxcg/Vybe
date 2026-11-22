import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react';
import type { Pick, Row } from '../contract';
import { HeroCard } from './HeroCard';
import './HeroCarousel.css';

const ORDER: Pick[] = ['best', 'runner_up', 'wildcard'];
const GAP_PX = 8;

interface Props {
  rows: Row[];
  nowMs: number;
  student: boolean;
  onOpen: (row: Row, e: MouseEvent<HTMLElement>) => void;
}

export function HeroCarousel({ rows, nowMs, student, onOpen }: Props) {
  const picks = ORDER.flatMap((pick) => rows.filter((r) => r.pick === pick));
  const trackRef = useRef<HTMLDivElement>(null);
  const raf = useRef(0);
  const [active, setActive] = useState(0);

  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  if (picks.length === 0) return null;

  // One state update per frame at most, even while the scroll is still settling.
  const onScroll = () => {
    if (raf.current) return;
    raf.current = requestAnimationFrame(() => {
      raf.current = 0;
      const track = trackRef.current;
      const card = track?.firstElementChild as HTMLElement | null;
      if (!track || !card) return;
      setActive(Math.round(track.scrollLeft / (card.offsetWidth + GAP_PX)));
    });
  };

  // Keyboard: left/right step between picks when the carousel itself is focused.
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    const track = trackRef.current;
    const card = track?.firstElementChild as HTMLElement | null;
    if (!track || !card) return;
    e.preventDefault();
    const step = card.offsetWidth + GAP_PX;
    track.scrollBy({ left: e.key === 'ArrowRight' ? step : -step, behavior: 'smooth' });
  };

  return (
    <section className="hero" aria-label="Your picks">
      <div
        ref={trackRef}
        className="hero-track"
        role="group"
        aria-roledescription="carousel"
        aria-label="Picked for you"
        tabIndex={0}
        onScroll={onScroll}
        onKeyDown={onKeyDown}
      >
        {picks.map((row) => (
          <HeroCard key={row.id} row={row} nowMs={nowMs} student={student} onOpen={onOpen} />
        ))}
      </div>
      {picks.length > 1 && (
        <div className="hero-dots" aria-hidden="true">
          {picks.map((row, i) => (
            <span key={row.id} className={i === Math.min(active, picks.length - 1) ? 'is-on' : undefined} />
          ))}
        </div>
      )}
    </section>
  );
}
