import { useState, type MouseEvent } from 'react';
import type { Pick, Row } from '../contract';
import { formatPrice, when } from '../lib/format';
import { formatHM, MINUTE, minutesUntil } from '../lib/time';
import { useVenueColors, venueStyle } from '../lib/venueColors';
import { FuseLine } from './FuseLine';
import { Grain } from './Grain';
import { RollingNumber } from './RollingNumber';
import { StatusText } from './StatusText';
import './HeroCard.css';

const PICK_LABEL: Record<Pick, string> = {
  best: 'Your best pick',
  runner_up: 'Runner-up',
  wildcard: 'Wildcard',
};

const FUSE_WINDOW_MIN = 60;

interface Props {
  row: Row;
  nowMs: number;
  student: boolean;
  onOpen: (row: Row, e: MouseEvent<HTMLElement>) => void;
}

function LeaveText({ row, nowMs }: { row: Row; nowMs: number }) {
  if (row.status === 'delayed_rain') return <>Outdoors, raining</>;
  const mins = minutesUntil(row.leave_by, nowMs);
  if (mins <= 0) return <>Leave now</>;
  if (mins >= 60) return <>Leave by {formatHM(row.leave_by)}</>;
  return (
    <>
      Leave in <RollingNumber value={mins} /> min
    </>
  );
}

export function HeroCard({ row, nowMs, student, onOpen }: Props) {
  const price = formatPrice(row, student);
  const fuse = (Date.parse(row.leave_by) - nowMs) / (FUSE_WINDOW_MIN * MINUTE);
  // Photo cards only once the image has actually loaded; otherwise the poster layout.
  const [photo, setPhoto] = useState<'loading' | 'ok' | 'failed'>(row.photo_url ? 'loading' : 'failed');
  const reason = row.reasons[0]?.text;
  const colors = useVenueColors(row);

  return (
    <button
      className={`hero-card${photo === 'ok' ? ' hero-card--photo' : ''}`}
      type="button"
      style={venueStyle(colors)}
      data-row-id={row.id}
      onClick={(e) => onOpen(row, e)}
    >
      {row.photo_url && photo !== 'failed' && (
        <span className="hero-card-photo" aria-hidden="true">
          <img src={row.photo_url} alt="" onLoad={() => setPhoto('ok')} onError={() => setPhoto('failed')} />
        </span>
      )}

      <span className="hero-card-top">
        {row.pick && (
          <span className={`hero-tag${row.pick === 'best' ? ' hero-tag--best' : ''}`}>{PICK_LABEL[row.pick]}</span>
        )}
        <span className="hero-tag">
          <StatusText status={row.status} />
        </span>
      </span>

      <span className="hero-card-when">
        <span className="hero-card-dlabel t-label">{when(row).label}</span>
        <span className="hero-card-time tnum">{when(row).value}</span>
      </span>

      <span className="t-section hero-card-name">{row.name}</span>
      {reason && <span className="t-secondary hero-card-reason">{reason}</span>}

      <span className="hero-card-bottom">
        <span className="t-key tnum">
          <LeaveText row={row} nowMs={nowMs} />
        </span>
        <span className="t-secondary hero-card-meta">
          <span>{row.walk_min} min walk</span>
          {price && <span>{price}</span>}
        </span>
      </span>

      <FuseLine fraction={fuse} />
      <Grain />
    </button>
  );
}
