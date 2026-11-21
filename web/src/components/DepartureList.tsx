import { useRef, type MouseEvent } from 'react';
import type { Row } from '../contract';
import { dayWord, MINUTE } from '../lib/time';
import { DepartureRow } from './DepartureRow';
import './DepartureList.css';

const SOON_MIN = 30;
/** A departed row shows "Departed" this long, then collapses away. */
const DEPARTED_SHOW_MS = 3000;
const COLLAPSE_MS = 320;

interface Props {
  rows: Row[];
  byCategory: boolean;
  shared: boolean;
  nowMs: number;
  wallMs: number;
  onOpen: (row: Row, e: MouseEvent<HTMLElement>) => void;
}

type Phase = 'live' | 'collapsing' | 'gone';

/** Remembers when each row was first seen departed (device time), to stage its exit. */
function useDepartedPhase(rows: Row[], wallMs: number): (row: Row) => Phase {
  const seen = useRef(new Map<string, number>());
  for (const r of rows) {
    if (r.status === 'departed') {
      if (!seen.current.has(r.id)) seen.current.set(r.id, wallMs);
    } else {
      seen.current.delete(r.id); // e.g. time-travel back
    }
  }
  return (row) => {
    const since = seen.current.get(row.id);
    if (since === undefined) return 'live';
    const age = wallMs - since;
    if (age < DEPARTED_SHOW_MS) return 'live';
    return age < DEPARTED_SHOW_MS + COLLAPSE_MS ? 'collapsing' : 'gone';
  };
}

export function DepartureList({ rows, byCategory, shared, nowMs, wallMs, onOpen }: Props) {
  const phaseOf = useDepartedPhase(rows, wallMs);
  const rest = rows
    .filter((r) => !r.pick)
    .map((row) => ({ row, phase: phaseOf(row) }))
    .filter((r) => r.phase !== 'gone');
  const cutoff = nowMs + SOON_MIN * MINUTE;
  // Urgent things first; walk-in places that are simply open come next; timed things later on.
  const soon = (r: { row: Row }) => Date.parse(r.row.leave_by) <= cutoff;
  const timeGroups = [
    { title: 'Next 30 minutes', items: rest.filter(soon) },
    { title: 'Open now', items: rest.filter((r) => !soon(r) && r.row.timed === false && !r.row.needs_booking) },
    { title: 'Book for tonight', items: rest.filter((r) => !soon(r) && r.row.timed === false && r.row.needs_booking) },
    { title: `Later ${dayWord(nowMs)}`, items: rest.filter((r) => !soon(r) && r.row.timed !== false) },
  ];
  const categories = [...new Set(rest.map(({ row }) => row.group ?? 'Other'))];
  const groups = (shared ? [{ title: 'More matches', items: rest }] : byCategory && rest.some(({ row }) => row.group)
    ? categories.map((title) => ({
        title,
        items: timeGroups.flatMap(({ items }) =>
          items.filter(({ row }) => (row.group ?? 'Other') === title),
        ),
      }))
    : timeGroups
  ).filter((group) => group.items.length > 0);

  return (
    <div className="dlist">
      {groups.map((group) => (
        <section key={group.title} className="dlist-group">
          <h2 className="t-sub dlist-title">{group.title}</h2>
          <ul className="dlist-rows">
            {group.items.map(({ row, phase }) => (
              <li key={row.id} className={`dlist-item${phase === 'collapsing' ? ' is-collapsing' : ''}`}>
                <div className="dlist-item-inner">
                  <DepartureRow row={row} nowMs={nowMs} onOpen={onOpen} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
