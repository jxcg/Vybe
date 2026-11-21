import { useEffect, useRef, useState } from 'react';
import { Bookmark, ChevronLeft, Navigation, Pause, Ticket as TicketIcon, Volume2, X } from 'lucide-react';
import type { Row } from '../contract';
import { ago, formatPrice, hostname, when } from '../lib/format';
import { formatHM, MINUTE } from '../lib/time';
import { darken, useVenueColors, venueStyle } from '../lib/venueColors';
import { Grain } from './Grain';
import { NextStrip } from './NextStrip';
import { ReasonIcon } from './ReasonIcon';
import { StatusText } from './StatusText';
import './Ticket.css';
import './TicketClassic.css';

/** Poster tickets darken by up to this much OKLCH lightness over the last half hour before leave time. */
const DARKEN_MAX = 0.04;
const DARKEN_WINDOW_MIN = 30;

/** Plays the card's Voxtral voiceover (mp3 from the pipeline). One tap plays, another stops. */
function VoiceoverButton({ url }: { url: string }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  useEffect(() => () => audio.current?.pause(), []); // stop when the ticket closes
  const toggle = () => {
    if (!audio.current) {
      audio.current = new Audio(url);
      audio.current.onended = () => setPlaying(false);
    }
    if (playing) {
      audio.current.pause();
      audio.current.currentTime = 0;
      setPlaying(false);
    } else {
      void audio.current.play().then(() => setPlaying(true), () => setPlaying(false));
    }
  };
  return (
    <button type="button" className="ticket-circle" aria-label={playing ? 'Stop voiceover' : 'Play voiceover'} onClick={toggle}>
      {playing ? <Pause size={20} strokeWidth={2} aria-hidden="true" /> : <Volume2 size={20} strokeWidth={2} aria-hidden="true" />}
    </button>
  );
}

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

      </div>
      <Grain />

      <div className="ticket-top ticket-fade">
        <button type="button" className="ticket-circle" aria-label="Back to the board" onClick={onBack}>
          <ChevronLeft size={20} strokeWidth={2} aria-hidden="true" />
        </button>
        {row.voiceover_url && <VoiceoverButton url={row.voiceover_url} />}
      </div>

      {/* Classic "For You" layout: badge, name, scores, chips, then a big leave-by with Directions. */}
      <div className="ticket-body ticket-fade">
        <span className={`ticket-badge ticket-badge--${row.status}`}>
          <StatusText status={row.status} />
        </span>
        <h2 className="ticket-name">{row.name}</h2>
        <p className="ticket-meta">
          {row.walk_min} min walk
          {price && <span className="ticket-dot">·</span>}
          {price}
          <span className="ticket-dot">·</span>
          {when(row).line}
        </p>
        <p className="ticket-scores">
          <strong>{Math.round(row.score * 10)}% match</strong>
          {row.rating !== null && (
            <>
              <span className="ticket-dot">·</span>★ {row.rating} on Google
            </>
          )}
        </p>
        {row.pitch && <p className="ticket-pitch">{row.pitch}</p>}
        {row.reasons.length > 0 && (
          <ul className="ticket-chips">
            {row.reasons.slice(0, 3).map((r) => (
              <li key={r.text}>
                <ReasonIcon name={r.icon} />
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="ticket-side" role="group" aria-label="Actions">
          <button
            type="button"
            className={`ticket-circle ticket-circle--lg${liked ? ' is-on' : ''}`}
            aria-pressed={liked}
            aria-label={liked ? 'Saved' : 'Save for later'}
            onClick={onLike}
          >
            <Bookmark size={20} strokeWidth={2} fill={liked ? 'currentColor' : 'none'} aria-hidden="true" />
          </button>
          {row.booking_url && (
            <a className="ticket-circle ticket-circle--lg" href={row.booking_url} target="_blank" rel="noreferrer" aria-label="Book">
              <TicketIcon size={20} strokeWidth={2} aria-hidden="true" />
            </a>
          )}
          <button type="button" className="ticket-circle ticket-circle--lg" aria-label="Not for me" onClick={onSkip}>
            <X size={20} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>

        <div className="ticket-leave">
          <div className="ticket-leave-by">
            <span className="ticket-leave-label">LEAVE BY</span>
            <span className="ticket-leave-time tnum">{formatHM(row.leave_by)}</span>
          </div>
          <a className="ticket-directions" href={directions} target="_blank" rel="noreferrer">
            Directions
            <Navigation size={16} strokeWidth={2} aria-hidden="true" />
          </a>
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
