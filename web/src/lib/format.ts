import { formatHM } from './time';
import type { Category, Row, Status } from '../contract';

export const STATUS_LABEL: Record<Status, string> = {
  on_time: 'On time',
  boarding: 'Boarding',
  last_call: 'Last call',
  departed: 'Departed',
  delayed_rain: 'Delayed',
  cancelled: 'Cancelled',
};

export const CATEGORY_LABEL: Record<Category, string> = {
  comedy: 'Comedy',
  games: 'Games',
  food: 'Food',
  music: 'Music',
  culture: 'Culture',
  bar: 'Bar',
  other: 'Other',
};

function pounds(n: number): string {
  return Number.isInteger(n) ? `£${n}` : `£${n.toFixed(2)}`;
}

/** "Free", "£8", "£8 student" — or null when the price is unknown. */
export function formatPrice(row: Row, student: boolean): string | null {
  if (row.price_unknown) return 'Price unknown';
  if (row.your_price === null) return row.price_level ? '£'.repeat(row.price_level) : null;
  if (row.your_price === 0) return 'Free';
  const base = pounds(row.your_price);
  return student && row.was_price !== null ? `${base} student` : base;
}

/** "just now", "4 min ago", "2 h ago" relative to the board's clock. */
export function ago(iso: string, nowMs: number): string {
  const mins = Math.floor((nowMs - Date.parse(iso)) / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  return `${Math.floor(mins / 60)} h ago`;
}

/** "timeout.com" from a full URL, or null if it can't be parsed. */
export function hostname(url: string): string | null {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

/**
 * How to show a row's time. Shows and gigs have a real start time; walk-in places (food, bars,
 * museums) don't, so they say "Open" with their closing time instead of a misleading big time.
 */
export function when(row: Row): { value: string; label: string; line: string } {
  if (row.timed !== false) {
    const t = formatHM(row.departure_time);
    return { value: t, label: row.departure_label, line: `${row.departure_label} ${t}` };
  }
  if (row.needs_booking) return { value: 'Book', label: 'Book ahead', line: 'Book ahead' };
  const label =
    row.departure_label === 'Open 24 hours' ? 'Open 24 hours' : `Open till ${formatHM(row.departure_time)}`;
  return { value: 'Open', label, line: label };
}
