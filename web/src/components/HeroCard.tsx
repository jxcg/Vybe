import { useState, type MouseEvent } from 'react';
import { usePlacePhoto } from '../lib/placePhoto';
import type { Pick, Row } from '../contract';
import { formatPrice, when } from '../lib/format';
import { formatHM, MINUTE, minutesUntil } from '../lib/time';
import { useVenueColors, venueStyle } from '../lib/venueColors';
import { FuseLine } from './FuseLine';
import { RollingNumber } from './RollingNumber';
import { VenueRating } from './VenueRating';
import { StatusText } from './StatusText';
import './HeroCard.css';

const PICK_LABEL: Record<Pick, string> = {
  best: 'Your best pick',
  runner_up: 'Runner-up',
  wildcard: 'Wildcard',
};

const FUSE_WINDOW_MIN = 60;

/** Strong matches (8/10 and up) get a barely-there shine. */
const TOP_SCORE = 8;

interface Props {
  row: Row;
  nowMs: number;
  student: boolean;
  onOpen: (row: Row, e: MouseEvent<HTMLElement>) => void;
}

function LeaveText({ row, nowMs }: { row: Row; nowMs: number }) {
  if (row.status === 'delayed_rain') return <>Outdoors, raining</>;
  if (row.timed === false) return <>{row.needs_booking ? 'Check available booking times' : 'No fixed start time'}</>;
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
  const { url: photoUrl, google } = usePlacePhoto(row);
  const [loadedPhoto, setLoadedPhoto] = useState<string | null>(null);
  const [failedPhoto, setFailedPhoto] = useState<string | null>(null);
  const isPhoto = Boolean(photoUrl && photoUrl === loadedPhoto);
  const colors = useVenueColors(row, isPhoto ? photoUrl : null);

  return (
    <button
      className={`hero-card${isPhoto ? ' hero-card--photo' : ''}${row.score >= TOP_SCORE ? ' is-top' : ''}`}
      type="button"
      style={venueStyle(colors, row.photo_fade_start)}
      data-row-id={row.id}
      onClick={(e) => onOpen(row, e)}
    >
      <span className="hero-card-media">
        {photoUrl && photoUrl !== failedPhoto && (
          <img
            className="hero-card-photo"
            src={photoUrl}
            alt=""
            onLoad={() => setLoadedPhoto(photoUrl)}
            onError={() => setFailedPhoto(photoUrl)}
          />
        )}
        <span className="hero-card-top">
          {row.pick && <span className="hero-tag">{PICK_LABEL[row.pick]}</span>}
          {row.status !== 'on_time' && (
            <span className="hero-tag hero-tag--status">
              <StatusText status={row.status} />
            </span>
          )}
        </span>
      </span>

      <span className="hero-card-content">
        <span className="hero-card-meta">{when(row).line}</span>
        <span className="hero-card-name">
          <span className="hero-card-name-text" title={row.name}>{row.name}</span>
          <VenueRating rating={row.rating} />
        </span>
        <span className="hero-card-meta">
          <span>{row.walk_min} min walk</span>
          {price && <span>{price}</span>}
        </span>
        <span className="hero-card-leave tnum">
          <LeaveText row={row} nowMs={nowMs} />
        </span>
        {isPhoto && (google || row.photo_credit) && (
          <span className="card-photo-credit">
            {google ? ['Google Maps', ...google.authors.map((author) => author.displayName)].join(' · ') : `Photo · ${row.photo_credit}`}
          </span>
        )}
      </span>
      {row.timed !== false && <FuseLine fraction={fuse} />}
    </button>
  );
}
