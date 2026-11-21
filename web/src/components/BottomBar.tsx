import { Mic } from 'lucide-react';
import './BottomBar.css';

interface Props {
  onFilters: () => void;
}

export function BottomBar({ onFilters }: Props) {
  return (
    <div className="bottombar">
      <button className="bottombar-action" type="button" onClick={onFilters}>
        <Mic size={18} strokeWidth={2} aria-hidden="true" />
        Change your vibe
      </button>
    </div>
  );
}
