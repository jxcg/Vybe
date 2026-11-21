import { useEffect, useRef, useState } from 'react';
import { Loader2, Mic, SlidersHorizontal, Square } from 'lucide-react';
import { useStore } from '../state/store';
import { useTalk } from '../state/useTalk';
import './BottomBar.css';

const TALK_MAX_MS = 15_000;
const THINKING_TIMEOUT_MS = 8_000;

interface Props {
  onFilters: () => void;
}

/** Board controls: change your vybe, or tell the board what you want ("cheaper, nothing outdoors"). */
export function BottomBar({ onFilters }: Props) {
  const { state } = useStore();
  const [phase, setPhase] = useState<'idle' | 'listening' | 'thinking'>('idle');
  const cap = useRef<number | undefined>(undefined);
  const talk = useTalk('command', () => setPhase('idle'));

  // The server answered (chips arrive with the re-ranked board): done thinking.
  useEffect(() => setPhase((p) => (p === 'thinking' ? 'idle' : p)), [state.chipsSeq]);
  useEffect(() => {
    if (phase !== 'thinking') return;
    const t = window.setTimeout(() => setPhase('idle'), THINKING_TIMEOUT_MS);
    return () => window.clearTimeout(t);
  }, [phase]);
  useEffect(() => () => window.clearTimeout(cap.current), []);

  const end = () => {
    window.clearTimeout(cap.current);
    talk.stop();
    setPhase('thinking');
  };
  const onTalk = () => {
    if (phase === 'listening') return end();
    if (phase === 'thinking') return;
    talk.start();
    setPhase('listening');
    cap.current = window.setTimeout(end, TALK_MAX_MS);
  };

  return (
    <div className="bottombar">
      <button className="icon-btn icon-btn--lg" type="button" aria-label="Change your vybe" onClick={onFilters}>
        <SlidersHorizontal size={20} strokeWidth={2} />
      </button>
      <button
        className={`bottombar-talk${phase !== 'idle' ? ` is-${phase}` : ''}`}
        type="button"
        aria-pressed={phase === 'listening'}
        onClick={onTalk}
      >
        {phase === 'listening' ? (
          <Square size={16} strokeWidth={2} aria-hidden="true" />
        ) : phase === 'thinking' ? (
          <Loader2 size={18} strokeWidth={2} aria-hidden="true" className="spin" />
        ) : (
          <Mic size={18} strokeWidth={2} aria-hidden="true" />
        )}
        {phase === 'listening' ? 'Listening… tap when done' : phase === 'thinking' ? 'Got it…' : 'Tap to talk'}
      </button>
    </div>
  );
}
