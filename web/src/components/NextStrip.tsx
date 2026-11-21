import { ChevronUp } from 'lucide-react';
import type { Row } from '../contract';
import { formatHM } from '../lib/time';
import { useVenueColors, venueStyle } from '../lib/venueColors';
import './NextStrip.css';

/** A peek of the next departure in its own colour; tap to slide up to it. */
export function NextStrip({ row, onClick }: { row: Row; onClick: () => void }) {
  const colors = useVenueColors(row);
  return (
    <button type="button" className="next-strip" style={venueStyle(colors)} onClick={onClick}>
      <span className="next-strip-label">Next</span>
      <span className="next-strip-time tnum">{formatHM(row.departure_time)}</span>
      <span className="next-strip-name">{row.name}</span>
      <ChevronUp size={18} strokeWidth={2} aria-hidden="true" />
    </button>
  );
}
