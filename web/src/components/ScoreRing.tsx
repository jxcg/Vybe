import type { CSSProperties } from 'react';
import './ScoreRing.css';

const R = 30;
const C = 2 * Math.PI * R;

/** "9/10 for you": a thin ring whose arc draws in to the score. */
export function ScoreRing({ score }: { score: number }) {
  const value = Math.round(Math.min(10, Math.max(0, score)));
  const offset = C * (1 - value / 10);
  return (
    <div className="score" role="img" aria-label={`${value} out of 10 for you`}>
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <circle className="score-track" cx="32" cy="32" r={R} />
        <circle
          className="score-arc"
          cx="32"
          cy="32"
          r={R}
          strokeDasharray={C}
          strokeDashoffset={offset}
          style={{ '--c': `${C}px` } as CSSProperties}
          transform="rotate(-90 32 32)"
        />
      </svg>
      <span className="score-text" aria-hidden="true">
        <span className="score-num tnum">{value}/10</span>
        <span className="score-sub">for you</span>
      </span>
    </div>
  );
}
