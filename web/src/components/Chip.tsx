import { Ban, X } from 'lucide-react';
import './Chip.css';

export type ChipTone = 'into' | 'notinto' | 'neutral';

interface Props {
  label: string;
  tone: ChipTone;
  leaving: boolean;
  delay: number;
  onRemove: () => void;
  onExited: () => void;
}

export function Chip({ label, tone, leaving, delay, onRemove, onExited }: Props) {
  return (
    <span
      className={`chip chip--${tone}${leaving ? ' chip--leaving' : ''}`}
      style={leaving ? undefined : { animationDelay: `${delay}ms` }}
      onAnimationEnd={(e) => {
        if (leaving && e.target === e.currentTarget) onExited();
      }}
    >
      {tone === 'notinto' && <Ban size={12} strokeWidth={2} aria-hidden="true" />}
      <span>{label}</span>
      <button
        type="button"
        className="chip-x"
        aria-label={`Remove ${label}`}
        onClick={onRemove}
        disabled={leaving}
      >
        <X size={14} strokeWidth={2} aria-hidden="true" />
      </button>
    </span>
  );
}
