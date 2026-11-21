import type { Row } from '../contract';

const TZ = 'Europe/London';
export const MINUTE = 60_000;

const hmFormat = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

const partsFormat = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

function londonParts(d: Date) {
  const p: Record<string, number> = {};
  for (const part of partsFormat.formatToParts(d)) p[part.type] = Number(part.value);
  return { y: p.year, mo: p.month, d: p.day, h: p.hour, mi: p.minute };
}

/** The instant at which London wall-clock reads `hhmm` on the London date of `ref`. */
export function londonWallTime(ref: Date, hhmm: string): Date {
  const { y, mo, d } = londonParts(ref);
  const [h, m] = hhmm.split(':').map(Number);
  const guess = Date.UTC(y, mo - 1, d, h, m);
  const seen = londonParts(new Date(guess));
  const seenAsUtc = Date.UTC(seen.y, seen.mo - 1, seen.d, seen.h, seen.mi);
  return new Date(guess - (seenAsUtc - guess));
}

/** "today" in the daytime, "tonight" from 17:00 until 05:00 (London time). */
export function dayWord(nowMs: number): 'today' | 'tonight' {
  const hour = Number(formatHM(nowMs).slice(0, 2));
  return hour >= 17 || hour < 5 ? 'tonight' : 'today';
}

/** "19:30" in London time. */
export function formatHM(t: string | number | Date): string {
  return hmFormat.format(typeof t === 'string' ? new Date(t) : t);
}

/** Whole minutes from `nowMs` until `iso` (floored, may be negative). */
export function minutesUntil(iso: string, nowMs: number): number {
  return Math.floor((Date.parse(iso) - nowMs) / MINUTE);
}

/** Display-only countdown derived from leave_by. Never decides status. */
export function leaveHint(row: Row, nowMs: number): string {
  if (row.status === 'delayed_rain') return 'outdoors, raining';
  const mins = minutesUntil(row.leave_by, nowMs);
  if (mins <= 0) return 'leave now';
  if (mins < 60) return `leave in ${mins} min`;
  return `leave by ${formatHM(row.leave_by)}`;
}
