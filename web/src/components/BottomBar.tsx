import { Mic, SlidersHorizontal } from 'lucide-react';
import './BottomBar.css';

interface Props {
  onFilters: () => void;
}

export function BottomBar({ onFilters }: Props) {
  return (
    <div className="bottombar">
      <button className="icon-btn icon-btn--lg" type="button" aria-label="Change your vybe" onClick={onFilters}>
        <SlidersHorizontal size={20} strokeWidth={2} />
      </button>
      <button className="bottombar-talk" type="button">
        <Mic size={18} strokeWidth={2} aria-hidden="true" />
        Tap to talk
      </button>
    </div>
  );
}
