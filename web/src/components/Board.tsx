import { useRef, useState, type MouseEvent } from 'react';
import { Shuffle } from 'lucide-react';
import { clearBoardFilters, toPrefs } from '../lib/vybe';
import { isMock } from '../net/socket';
import type { Row } from '../contract';
import { useStore } from '../state/store';
import { useClock } from '../state/useClock';
import { useWakeLock } from '../state/useWakeLock';
import { BoardHeader } from './BoardHeader';
import { BottomBar } from './BottomBar';
import { DepartureList } from './DepartureList';
import { HeroCarousel } from './HeroCarousel';
import { Meetup } from './Meetup';
import './Board.css';

const GROUP_ORDER = ['Food', 'Drinks', 'Entertainment', 'Culture', 'Outdoors'];

function fallbackIntro(row: Row, previous: string | null): string {
  const group = GROUP_ORDER.find((name) => name === row.group);
  const isLiveEntertainment = row.category === 'music' || row.category === 'comedy';
  const category = group && (group !== 'Entertainment' || isLiveEntertainment) ? group.toLowerCase() : 'intro';
  const base = `/audio/vybe-radio-${category}`;
  const clips = [`${base}.mp3`, `${base}-alt.mp3`].filter((url) => url !== previous);
  return clips[Math.floor(Math.random() * clips.length)];
}

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
  const { state, dispatch, send, enterRoom, join } = useStore();
  const { board, vybe, shared } = state;
  const [showInvite, setShowInvite] = useState(false);
  const hasFilters = Boolean(board?.group || vybe.into.length || vybe.notInto.length ||
    (vybe.budget !== null && vybe.budget !== 999) || vybe.vibe);
  const resetFilters = () => {
    const cleared = clearBoardFilters(vybe);
    dispatch({ type: 'reset_filters', vybe: cleared });
    setEmptySurprise(false);
    if (shared) join(cleared);
    else if (board?.group) send({ type: 'show', group: null });
  };
  const inviteFriends = () => {
    if (shared) {
      setShowInvite((open) => !open);
      return;
    }
    dispatch({ type: 'clear_room_error' });
    setShowInvite(true);
    enterRoom({ type: 'room_create', name: 'Host', prefs: toPrefs(vybe), liked: state.liked });
  };
  const rows = !shared && board?.count === 4
    ? board.rows.map((row) => row.pick && row.pick !== 'best' ? { ...row, pick: null } : row)
    : board?.rows ?? [];
  const { nowMs, wallMs } = useClock(board, state.boardAt);
  const lastSurprise = useRef<string | null>(null);
  const lastIntro = useRef<string | null>(null);
  const [emptySurprise, setEmptySurprise] = useState(false);
  useWakeLock();

  const eligible = rows.filter((row) =>
    row.status !== 'departed' && row.status !== 'cancelled' &&
    row.status !== 'delayed_rain' && !row.over_budget && Date.parse(row.leave_by) >= nowMs
  );

  const surprise = (e: MouseEvent<HTMLButtonElement>) => {
    const pool = eligible.length > 1 ? eligible.filter((row) => row.id !== lastSurprise.current) : eligible;
    const pick = pool[Math.floor(Math.random() * pool.length)];
    if (!pick) {
      setEmptySurprise(true);
      return;
    }

    setEmptySurprise(false);
    lastSurprise.current = pick.id;
    const fallback = fallbackIntro(pick, lastIntro.current);
    const venueIntro = pick.voiceover_url === lastIntro.current ? null : pick.voiceover_url;
    const intro = venueIntro || fallback;
    lastIntro.current = intro;
    const audio = new Audio(intro);
    void audio.play().catch((error: unknown) => {
      if (!(error instanceof DOMException) || error.name !== 'NotSupportedError' || !venueIntro) return;
      if (lastIntro.current === intro) lastIntro.current = fallback;
      audio.src = fallback;
      return audio.play().catch(() => undefined);
    });
    openTicket(pick, e, audio);
  };

  // Expand the ticket from where the finger landed (or the element's centre for keyboard taps).
  const openTicket = (row: Row, e: MouseEvent<HTMLElement>, radioAudio?: HTMLAudioElement) => {
    const r = e.currentTarget.getBoundingClientRect();
    const fromPointer = e.detail > 0;
    dispatch({
      type: 'open_ticket',
      ticket: {
        id: row.id,
        radioAudio,
        x: fromPointer ? e.clientX : r.left + r.width / 2,
        y: fromPointer ? e.clientY : r.top + r.height / 2,
      },
    });
  };

  return (
    <div className="board">
      <main className="board-scroll">
        <BoardHeader
          board={board}
          nowMs={nowMs}
          onInvite={!isMock && state.conn === 'open' && !state.roomConnecting && board ? inviteFriends : undefined}
          inviteOpen={Boolean(shared && showInvite)}
        >
          {board && (
            <div className="board-radio">
              <button type="button" className="board-radio-button" onClick={surprise}>
                <Shuffle size={16} aria-hidden="true" />
                Surprise me
              </button>
              <span role="status">
                {emptySurprise && eligible.length === 0 ? 'Nothing else for today. Try changing your filters.' : ''}
              </span>
            </div>
          )}
        </BoardHeader>
        <Meetup showInvite={showInvite} />
        {!board && <p className="board-wait">Finding what{'\u2019'}s on near you{'\u2026'}</p>}
        {board && (
          <>
            {!shared && board.groups && (
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
              shared={Boolean(shared)}
              nowMs={nowMs}
              wallMs={wallMs}
              onOpen={openTicket}
            />
            {board.count <= 3 && (
              <p className="board-end">
                {board.count ? 'Nothing else for today.' : shared
                  ? 'Nothing fits everyone yet. Change your vibe to try again.'
                  : 'Nothing to show for today.'}
              </p>
            )}
          </>
        )}
      </main>
      <BottomBar
        onFilters={() => dispatch({ type: 'go', screen: 'start' })}
        onReset={board && hasFilters && state.conn === 'open' && !state.roomConnecting ? resetFilters : undefined}
      />
    </div>
  );
}
