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

export function Board() {
  const { state, dispatch } = useStore();
  const { board, vybe } = state;
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
            <HeroCarousel rows={board.rows} nowMs={nowMs} student={vybe.student} onOpen={openTicket} />
            <DepartureList rows={board.rows} nowMs={nowMs} wallMs={wallMs} onOpen={openTicket} />
          </>
        )}
      </main>
      <BottomBar onFilters={() => dispatch({ type: 'go', screen: 'start' })} />
    </div>
  );
}
