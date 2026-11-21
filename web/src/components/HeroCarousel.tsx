import { useRef, useState, type MouseEvent } from 'react';
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
  const [active, setActive] = useState(0);
  if (picks.length === 0) return null;

  const onScroll = () => {
    const track = trackRef.current;
    const card = track?.firstElementChild as HTMLElement | null;
    if (!track || !card) return;
    setActive(Math.round(track.scrollLeft / (card.offsetWidth + GAP_PX)));
  };

  return (
    <section className="hero" aria-label="Your picks">
      <div ref={trackRef} className="hero-track" onScroll={onScroll}>
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
