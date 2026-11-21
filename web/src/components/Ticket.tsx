import { useState } from 'react';
import { Bookmark, ChevronLeft, Navigation, Ticket as TicketIcon, X } from 'lucide-react';
import type { Row } from '../contract';
import { ago, CATEGORY_LABEL, formatPrice, hostname } from '../lib/format';
import { formatHM, MINUTE } from '../lib/time';
import { darken, useVenueColors, venueStyle } from '../lib/venueColors';
import { Grain } from './Grain';
import { NextStrip } from './NextStrip';
import { ReasonIcon } from './ReasonIcon';
import { ScoreRing } from './ScoreRing';
import { StatusText } from './StatusText';
import './Ticket.css';

/** Poster tickets darken by up to this much OKLCH lightness over the last half hour before leave time. */
const DARKEN_MAX = 0.04;
const DARKEN_WINDOW_MIN = 30;

interface Props {
  row: Row;
  next: Row | null;
  nowMs: number;
  student: boolean;
  liked: boolean;
  onBack: () => void;
  onNext: () => void;
  onLike: () => void;
  onSkip: () => void;
}

export function Ticket({ row, next, nowMs, student, liked, onBack, onNext, onLike, onSkip }: Props) {
  const colors = useVenueColors(row);
  // Photo layout only once the image has actually loaded; otherwise the poster.
  const [photo, setPhoto] = useState<'loading' | 'ok' | 'failed'>(row.photo_url ? 'loading' : 'failed');
  const isPhoto = photo === 'ok';

  const minsToLeave = (Date.parse(row.leave_by) - nowMs) / MINUTE;
  const urgency = Math.min(1, Math.max(0, (DARKEN_WINDOW_MIN - minsToLeave) / DARKEN_WINDOW_MIN));
  const deep = isPhoto ? colors.deep : darken(colors.deep, DARKEN_MAX * urgency);

  const price = formatPrice(row, student);
  const directions = `https://www.google.com/maps/dir/?api=1&destination=${row.lat},${row.lng}&travelmode=walking`;
  const source = row.source_url ? hostname(row.source_url) : null;

  return (
    <article
      className={`ticket ${isPhoto ? 'ticket--photo' : 'ticket--poster'}`}
      style={venueStyle({ ...colors, deep })}
      aria-label={row.name}
      data-ticket-id={row.id}
    >
      <div className="ticket-media">
        {row.photo_url && photo !== 'failed' && (
          <img
            className="ticket-photo"
            src={row.photo_url}
            alt=""
            onLoad={() => setPhoto('ok')}
            onError={() => setPhoto('failed')}
          />
        )}
        {!isPhoto && (
          <div className="ticket-poster ticket-fade">
            <span className="ticket-poster-label">{row.departure_label}</span>
            <span className="ticket-poster-time tnum">{formatHM(row.departure_time)}</span>
          </div>
        )}
      </div>
      <Grain />

      <div className="ticket-top ticket-fade">
        <button type="button" className="ticket-circle" aria-label="Back to the board" onClick={onBack}>
          <ChevronLeft size={20} strokeWidth={2} aria-hidden="true" />
        </button>
        {/* TODO(P4): Volume2 circle that plays voiceover_url through the PCM player. */}
      </div>

      <div className="ticket-body ticket-fade">
        <p className="ticket-kicker">
          {CATEGORY_LABEL[row.category]}, {row.walk_min} min walk
        </p>
        <h2 className="ticket-name">{row.name}</h2>
        <p className="ticket-status">
          <StatusText status={row.status} className="ticket-status-word" />
          {isPhoto && (
            <span>
              {row.departure_label} {formatHM(row.departure_time)}
            </span>
          )}
          {price && <span>{price}</span>}
        </p>
        {row.pitch && <p className="ticket-pitch">{row.pitch}</p>}

        <div className="ticket-leave">
          <div className="ticket-leave-by">
            <span className="ticket-leave-label">Leave by</span>
            <span className="ticket-leave-time tnum">{formatHM(row.leave_by)}</span>
          </div>
          <ScoreRing score={row.score} />
        </div>

        {row.reasons.length > 0 && (
          <ul className="ticket-reasons">
            {row.reasons.slice(0, 3).map((r) => (
              <li key={r.text}>
                <span className="ticket-reason-icon">
                  <ReasonIcon name={r.icon} />
                </span>
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="ticket-actions">
          {row.booking_url ? (
            <a className="ticket-primary" href={row.booking_url} target="_blank" rel="noreferrer">
              <TicketIcon size={18} strokeWidth={2} aria-hidden="true" />
              Book
            </a>
          ) : (
            <a className="ticket-primary" href={directions} target="_blank" rel="noreferrer">
              <Navigation size={18} strokeWidth={2} aria-hidden="true" />
              Directions
            </a>
          )}
          {row.booking_url && (
            <a
              className="ticket-circle ticket-circle--lg"
              href={directions}
              target="_blank"
              rel="noreferrer"
              aria-label="Directions"
            >
              <Navigation size={20} strokeWidth={2} aria-hidden="true" />
            </a>
          )}
          <button
            type="button"
            className={`ticket-circle ticket-circle--lg${liked ? ' is-on' : ''}`}
            aria-pressed={liked}
            aria-label={liked ? 'Saved' : 'Save for later'}
            onClick={onLike}
          >
            <Bookmark size={20} strokeWidth={2} fill={liked ? 'currentColor' : 'none'} aria-hidden="true" />
          </button>
          <button type="button" className="ticket-circle ticket-circle--lg" aria-label="Not for me" onClick={onSkip}>
            <X size={20} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>

        <p className="ticket-checked">
          Checked {ago(row.checked_at, nowMs)}
          {source && row.source_url && (
            <>
              ,{' '}
              <a href={row.source_url} target="_blank" rel="noreferrer">
                {source}
              </a>
            </>
          )}
        </p>
      </div>

      {next && (
        <div className="ticket-fade">
          <NextStrip row={next} onClick={onNext} />
        </div>
      )}
    </article>
  );
}
