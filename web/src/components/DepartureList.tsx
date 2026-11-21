import { useRef, useState, type MouseEvent } from 'react';
import type { Row } from '../contract';
import { dayWord, MINUTE } from '../lib/time';
import { DepartureRow } from './DepartureRow';
import './DepartureList.css';

const SOON_MIN = 30;
/** A departed row shows "Departed" this long, then collapses away. */
const DEPARTED_SHOW_MS = 3000;
const COLLAPSE_MS = 320;
/** Browse order for the filter chips; only groups present on the board are shown. */
const GROUPS = ['Food', 'Drinks', 'Entertainment', 'Culture', 'Outdoors'];

interface Props {
  rows: Row[];
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

export function DepartureList({ rows, nowMs, wallMs, onOpen }: Props) {
  const phaseOf = useDepartedPhase(rows, wallMs);
  const [group, setGroup] = useState<string | null>(null);
  const present = GROUPS.filter((g) => rows.some((r) => !r.pick && r.group === g));
  const active = group && present.includes(group) ? group : null;
  const rest = rows
    .filter((r) => !r.pick && (!active || r.group === active))
    .map((row) => ({ row, phase: phaseOf(row) }))
    .filter((r) => r.phase !== 'gone');
  const cutoff = nowMs + SOON_MIN * MINUTE;
  const groups = [
    { title: 'Next 30 minutes', items: rest.filter((r) => Date.parse(r.row.leave_by) <= cutoff) },
    { title: `Later ${dayWord(nowMs)}`, items: rest.filter((r) => Date.parse(r.row.leave_by) > cutoff) },
  ].filter((g) => g.items.length > 0);

  return (
    <div className="dlist">
      {present.length > 1 && (
        <div className="dlist-filter" role="group" aria-label="Show">
          {[null, ...present].map((g) => (
            <button
              key={g ?? 'all'}
              type="button"
              className="dlist-chip"
              aria-pressed={active === g}
              onClick={() => setGroup(g)}
            >
              {g ?? 'All'}
              {g && <span className="dlist-chip-count">{rows.filter((r) => !r.pick && r.group === g).length}</span>}
            </button>
          ))}
        </div>
      )}
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
