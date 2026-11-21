import type { MouseEvent } from 'react';
import type { Row } from '../contract';
import { formatPrice, when } from '../lib/format';
import { leaveHint } from '../lib/time';
import { useVenueColors, venueStyle } from '../lib/venueColors';
import { VenueRating } from './VenueRating';
import { StatusText } from './StatusText';
import './DepartureRow.css';

interface Props {
  row: Row;
  nowMs: number;
  onOpen: (row: Row, e: MouseEvent<HTMLElement>) => void;
}

export function DepartureRow({ row, nowMs, onOpen }: Props) {
  // The list keeps prices bare; the hero card carries the "student" qualifier.
  const price = formatPrice(row, false);
  const colors = useVenueColors(row);

  return (
    <button
      className={`drow${row.score >= 8 ? ' is-top' : ''}`}
      type="button"
      style={venueStyle(colors)}
      data-row-id={row.id}
      onClick={(e) => onOpen(row, e)}
    >
      <span className={`drow-time tnum${row.timed === false ? ' drow-time--word' : ''}`}>{when(row).value}</span>
      <span className="drow-body">
        <span className="drow-line">
          <span className="drow-name">
            <span className="drow-dot" aria-hidden="true" />
            <span className="drow-name-text">{row.name}</span>
            <VenueRating rating={row.rating} />
          </span>
          <StatusText status={row.status} className="drow-status" />
        </span>
        <span className="drow-line t-secondary">
          <span className="drow-meta">
            <span className="drow-walk">{row.walk_min} min walk</span>
            {price && <span className={row.over_budget ? 'drow-over' : undefined}>{price}</span>}
          </span>
          <span className="drow-hint t-label tnum">{leaveHint(row, nowMs)}</span>
        </span>
      </span>
    </button>
  );
}
