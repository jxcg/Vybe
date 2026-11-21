import { useState } from 'react';
import './RollingNumber.css';

type Dir = 'up' | 'down';

/** One digit at its natural width. On change the old glyph slides out as the new one slides in. */
function Digit({ d, dir }: { d: string; dir: Dir }) {
  const [s, setS] = useState({ cur: d, prev: null as string | null, n: 0 });
  if (s.cur !== d) setS({ cur: d, prev: s.cur, n: s.n + 1 });

  return (
    <span className="rn-digit">
      {s.prev !== null && (
        <span
          key={`out${s.n}`}
          className={`rn-glyph rn-out rn-out--${dir}`}
          onAnimationEnd={() => setS((v) => ({ ...v, prev: null }))}
        >
          {s.prev}
        </span>
      )}
      <span key={`in${s.n}`} className={s.n ? `rn-glyph rn-in rn-in--${dir}` : 'rn-glyph'}>
        {s.cur}
      </span>
    </span>
  );
}

interface Props {
  value: number;
  /** zero-pad to this many digits, e.g. 2 for minutes */
  pad?: number;
}

/** Split-flap style number: digits roll vertically (300 ms) whenever the value changes. */
export function RollingNumber({ value, pad = 1 }: Props) {
  const text = String(Math.max(0, Math.round(value))).padStart(pad, '0');
  const [track, setTrack] = useState({ value, dir: 'down' as Dir });
  if (track.value !== value) setTrack({ value, dir: value > track.value ? 'up' : 'down' });
  const digits = text.split('');

  return (
    <span className="rn">
      <span className="sr-only">{text}</span>
      <span className="rn-digits" aria-hidden="true">
        {digits.map((d, i) => (
          // Key by place value so the units column persists when the digit count changes.
          <Digit key={digits.length - i} d={d} dir={track.dir} />
        ))}
      </span>
    </span>
  );
}
