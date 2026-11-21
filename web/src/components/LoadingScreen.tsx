import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Mic } from 'lucide-react';
import { useStore } from '../state/store';
import { handoff } from '../lib/handoff';
import { MORPH_EASE, prefersReducedMotion, shapeOf } from '../lib/morph';
import { Wordmark } from './Wordmark';
import './LoadingScreen.css';

/** Long enough to read a line and a half; never padded beyond that once the board is ready. */
const MIN_SHOW_MS = 1500;
const LINE_MS = 1300;
const GLIDE_MS = 520;
const EXIT_MS = 180;

const LINES = [
  'Looking around you',
  'Checking what’s still on',
  'Working out walking times',
  'Picking your best three',
];

/** A status line written in word by word; the previous line lifts away as the next arrives. */
function StatusLine({ index }: { index: number }) {
  const [s, setS] = useState({ cur: index, prev: null as number | null });
  if (s.cur !== index) setS({ cur: index, prev: s.cur });

  return (
    <p className="status-line" aria-live="polite">
      {s.prev !== null && (
        <span
          key={`out${s.prev}`}
          className="status-text status-text--out"
          aria-hidden="true"
          onAnimationEnd={() => setS((v) => ({ ...v, prev: null }))}
        >
          {LINES[s.prev]}
        </span>
      )}
      <span key={`in${s.cur}`} className="status-text">
        {LINES[s.cur].split(' ').map((word, i) => (
          <span key={i} className="status-word" style={{ animationDelay: `${80 + i * 55}ms` }}>
            {word}
          </span>
        ))}
      </span>
    </p>
  );
}

export function LoadingScreen() {
  const { state, dispatch } = useStore();
  const [line, setLine] = useState(0);
  const [minDone, setMinDone] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const orbRef = useRef<HTMLDivElement>(null);
  // Arriving from the mic: the orb starts as the mic (icon and all) and glides into place.
  const [fromMic] = useState(() => handoff.take('orb'));
  const ready = state.board !== null && minDone;

  useLayoutEffect(() => {
    const orb = orbRef.current;
    if (!orb || !fromMic || prefersReducedMotion()) return;
    const to = orb.getBoundingClientRect();
    const dx = fromMic.left + fromMic.width / 2 - (to.left + to.width / 2);
    const dy = fromMic.top + fromMic.height / 2 - (to.top + to.height / 2);
    const scale = fromMic.width / to.width;
    orb.animate([{ transform: `translate(${dx}px, ${dy}px) scale(${scale})` }, { transform: 'none' }], {
      duration: GLIDE_MS,
      easing: MORPH_EASE,
    });
  }, [fromMic]);

  useEffect(() => {
    const t = window.setTimeout(() => setMinDone(true), MIN_SHOW_MS);
    const lines = window.setInterval(() => setLine((i) => Math.min(i + 1, LINES.length - 1)), LINE_MS);
    return () => {
      window.clearTimeout(t);
      window.clearInterval(lines);
    };
  }, []);

  useEffect(() => {
    if (!ready) return;
    setLeaving(true);
    const t = window.setTimeout(() => {
      // The board takes the orb from here and folds it into its headline count.
      const orb = orbRef.current?.querySelector('.orb');
      if (orb) handoff.put('orb', shapeOf(orb));
      dispatch({ type: 'go', screen: 'board' });
    }, EXIT_MS);
    return () => window.clearTimeout(t);
  }, [ready, dispatch]);

  return (
    <div className={`loading${leaving ? ' is-leaving' : ''}${fromMic ? ' from-mic' : ''}`}>
      <div className="loading-bar">
        <Wordmark />
      </div>
      <div className="loading-center">
        <div ref={orbRef} className="orb-wrap" aria-hidden="true">
          <span className="orb-ring" />
          <span className="orb-ring" />
          <span className="orb-ring" />
          <span className="orb">{fromMic && <Mic className="orb-icon" strokeWidth={2} />}</span>
        </div>
        <h1 className="loading-title">Lining up what{'’'}s next</h1>
        <StatusLine index={line} />
      </div>
    </div>
  );
}
