import { formatRating } from '../lib/format';
import './VenueRating.css';

export function VenueRating({ rating }: { rating: number | null }) {
  const label = formatRating(rating);
  if (!label) return null;

  return (
    <span className="venue-rating tnum">
      <span className="sr-only">Venue rating </span>
      <span aria-hidden="true">★ </span>{label}
    </span>
  );
}
