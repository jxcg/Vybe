import { ArrowRight } from 'lucide-react';
import './FadePill.css';

interface Props {
  label: string;
  onClick: () => void;
}

/** The one lavender-fade button on a screen. */
export function FadePill({ label, onClick }: Props) {
  return (
    <button type="button" className="fade-pill" onClick={onClick}>
      {label}
      <ArrowRight size={18} strokeWidth={2} aria-hidden="true" />
    </button>
  );
}
