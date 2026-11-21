import type { MouseEvent } from 'react';
import type { Row } from '../contract';
import { useStore } from '../state/store';
import { useClock } from '../state/useClock';
import { useWakeLock } from '../state/useWakeLock';
import { BoardHeader } from './BoardHeader';
import { BottomBar } from './BottomBar';
import { DepartureList } from './DepartureList';
import { HeroCarousel } from './HeroCarousel';
import './Board.css';

const GROUP_ORDER = ['Food', 'Drinks', 'Entertainment', 'Culture', 'Outdoors'];

/** Browse by kind. The server rebuilds the whole board (picks, count, list) for the chosen group. */
function GroupFilter({ groups, active, onPick }: {
  groups: Record<string, number>;
  active: string | null;
  onPick: (group: string | null) => void;
}) {
  const present = GROUP_ORDER.filter((g) => groups[g] || g === active);
  if (present.length < 2 && !active) return null;
  const total = present.reduce((n, g) => n + (groups[g] ?? 0), 0);
  return (
    <div className="group-filter" role="group" aria-label="Show">
      {[null, ...present].map((g) => (
        <button key={g ?? 'all'} type="button" className="group-chip" aria-pressed={active === g} onClick={() => onPick(g)}>
          {g ?? 'Everything'}
          <span className="group-chip-count">{g ? groups[g] ?? 0 : total}</span>
        </button>
      ))}
    </div>
  );
}

export function Board() {
  const { state, dispatch, send } = useStore();
  const { board, vybe } = state;
  const rows = board?.count === 4
    ? board.rows.map((row) => row.pick && row.pick !== 'best' ? { ...row, pick: null } : row)
    : board?.rows ?? [];
  const { nowMs, wallMs } = useClock(board, state.boardAt);
  useWakeLock();

  // Expand the ticket from where the finger landed (or the element's centre for keyboard taps).
  const openTicket = (row: Row, e: MouseEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const fromPointer = e.detail > 0;
    dispatch({
      type: 'open_ticket',
      ticket: {
        id: row.id,
        x: fromPointer ? e.clientX : r.left + r.width / 2,
        y: fromPointer ? e.clientY : r.top + r.height / 2,
      },
    });
  };

  return (
    <div className="board">
      <main className="board-scroll">
        <BoardHeader board={board} nowMs={nowMs} />
        {!board && <p className="board-wait">Finding what{'\u2019'}s on near you{'\u2026'}</p>}
        {board && (
          <>
            {board.groups && (
              <GroupFilter
                groups={board.groups}
                active={board.group ?? null}
                onPick={(group) => send({ type: 'show', group })}
              />
            )}
            <HeroCarousel rows={rows} nowMs={nowMs} student={vybe.student} onOpen={openTicket} />
            <DepartureList
              rows={rows}
              byCategory={!board.group}
              nowMs={nowMs}
              wallMs={wallMs}
              onOpen={openTicket}
            />
            {board.count <= 3 && (
              <p className="board-end">
                {board.count ? 'Nothing else for today.' : 'Nothing to show for today.'}
              </p>
            )}
          </>
        )}
      </main>
      <BottomBar onFilters={() => dispatch({ type: 'go', screen: 'start' })} />
    </div>
  );
}
