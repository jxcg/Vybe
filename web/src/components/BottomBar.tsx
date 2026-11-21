import { Mic, RotateCcw } from 'lucide-react';
import './BottomBar.css';

interface Props {
  onFilters: () => void;
  onReset: () => void;
  resetDisabled: boolean;
}

export function BottomBar({ onFilters, onReset, resetDisabled }: Props) {
  return (
    <div className="bottombar">
      <button className="bottombar-action" type="button" onClick={onFilters}>
        <Mic size={18} strokeWidth={2} aria-hidden="true" />
        Change your vibe
      </button>
      <button className="bottombar-reset" type="button" onClick={onReset} disabled={resetDisabled}>
        <RotateCcw size={16} aria-hidden="true" />
        Reset &amp; redo
      </button>
    </div>
  );
}
