import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { Row } from '../contract';
import { prefersReducedMotion, whenDone } from '../lib/morph';
import { useStore, type OpenTicket } from '../state/store';
import { useClock } from '../state/useClock';
import { Ticket } from './Ticket';
import './TicketStack.css';

// Quick and even: open feels instant, close starts on the tap and is gone in about a quarter second.
const OPEN_MS = 420;
const CLOSE_MS = 260;
const FADE_MS = 90;
const SKIP_FADE_MS = 120;
const EASE_OUT = 'cubic-bezier(0.22, 1, 0.36, 1)';
const EASE_IN_OUT = 'cubic-bezier(0.4, 0, 0.2, 1)';
const HISTORY_KEY = 'vybeTicket';

const byDeparture = (a: Row, b: Row) => Date.parse(a.departure_time) - Date.parse(b.departure_time);

/** Circle big enough to cover the stack from point (x, y). */
function coverRadius(x: number, y: number, w: number, h: number): number {
  // +2px so the circle fully covers the corners before the clip is removed (no last-frame snap)
  return Math.hypot(Math.max(x, w - x), Math.max(y, h - y)) + 2;
}

/** On desktop the ticket is a centred panel over a dimmed board (see desktop.css). */
const isDesktop = () => window.matchMedia('(min-width: 1024px)').matches;
const PANEL_OPEN_MS = 300;
const PANEL_CLOSE_MS = 200;
// Must match .ticket-stack in desktop.css; the dim backdrop is the first shadow.
const PANEL_SHADOW = '0 0 0 100vmax rgb(20 18 26 / 0.45), 0 30px 80px -20px rgb(0 0 0 / 0.5)';
const PANEL_SHADOW_OFF = '0 0 0 100vmax rgb(20 18 26 / 0), 0 30px 80px -20px rgb(0 0 0 / 0)';
const panelFrames = [
  { opacity: 0, transform: 'translateX(-50%) translateY(18px) scale(0.97)', boxShadow: PANEL_SHADOW_OFF },
  { opacity: 1, transform: 'translateX(-50%) translateY(0) scale(1)', boxShadow: PANEL_SHADOW },
];

/**
 * Full-screen tickets for every departure still on, in time order, with vertical snap between them.
 * Opens as the venue colour expanding from the tapped point; closes back into the row it came from.
 */
export function TicketStack({ open }: { open: OpenTicket }) {
  const { state, dispatch, send } = useStore();
  const { nowMs } = useClock(state.board, state.boardAt);
  const stackRef = useRef<HTMLDivElement>(null);
  const closing = useRef(false);
  // Skipped here: hidden at once, without waiting for the server's next board.
  const [gone, setGone] = useState<string[]>([]);
  const arrived = useRef<string | null>(null);
  const allRows = state.board?.rows;

  const rows = useMemo(
    () =>
      (allRows ?? [])
        .filter((r) => !gone.includes(r.id) && (r.status !== 'departed' || r.id === open.id))
        .sort(byDeparture),
    [allRows, open.id, gone],
  );

  /** The tapped point, in the stack's own coordinates. */
  const localPoint = useCallback((x: number, y: number) => {
    const r = stackRef.current!.getBoundingClientRect();
    return { x: x - r.left, y: y - r.top, w: r.width, h: r.height };
  }, []);

  const animateClose = useCallback(() => {
    const stack = stackRef.current;
    if (!stack || closing.current) return;
    closing.current = true;
    const done = () => dispatch({ type: 'close_ticket' });
    if (prefersReducedMotion()) {
      void whenDone(stack.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, fill: 'forwards' })).then(done);
      return;
    }
    if (isDesktop()) {
      // Panel sinks and fades while the backdrop lifts: no clip, so nothing pops at the end.
      void whenDone(
        stack.animate([...panelFrames].reverse(), { duration: PANEL_CLOSE_MS, easing: EASE_IN_OUT, fill: 'forwards' }),
      ).then(done);
      return;
    }
    // Shrink back into the row we're looking at now (if it's on screen), else where we opened from.
    const id = stack.querySelectorAll<HTMLElement>('.ticket')[Math.round(stack.scrollTop / stack.clientHeight)]
      ?.dataset.ticketId;
    const target = id ? document.querySelector(`[data-row-id="${CSS.escape(id)}"]`) : null;
    const tr = target?.getBoundingClientRect();
    const usable = tr && tr.bottom > 0 && tr.top < window.innerHeight ? tr : null;
    const p = localPoint(
      usable ? usable.left + usable.width / 2 : open.x,
      usable ? usable.top + usable.height / 2 : open.y,
    );
    const r = coverRadius(p.x, p.y, p.w, p.h);

    // Text fades and the colour starts shrinking on the same frame: no pause before anything moves.
    stack.querySelectorAll('.ticket-fade').forEach((el) =>
      el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: FADE_MS, fill: 'forwards' }),
    );
    void whenDone(
      stack.animate(
        [{ clipPath: `circle(${r}px at ${p.x}px ${p.y}px)` }, { clipPath: `circle(0px at ${p.x}px ${p.y}px)` }],
        { duration: CLOSE_MS, easing: EASE_IN_OUT, fill: 'forwards' },
      ),
    ).then(done);
  }, [dispatch, localPoint, open.x, open.y]);

  /** Back button / Escape: animate straight away, then quietly drop our history entry. */
  const back = useCallback(() => {
    animateClose();
    if (history.state?.[HISTORY_KEY]) history.back(); // its popstate is ignored: we're already closing
  }, [animateClose]);

  // Open: jump to the tapped ticket, then expand the venue colour from the tap point.
  useLayoutEffect(() => {
    const stack = stackRef.current;
    if (!stack) return;
    const start = Math.max(0, rows.findIndex((r) => r.id === open.id));
    stack.scrollTop = start * stack.clientHeight;

    if (prefersReducedMotion()) {
      stack.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220 });
      return;
    }
    if (isDesktop()) {
      stack.animate(panelFrames, { duration: PANEL_OPEN_MS, easing: EASE_OUT });
    } else {
      const p = localPoint(open.x, open.y);
      const r = coverRadius(p.x, p.y, p.w, p.h);
      // Ease in-out: a fast-start ease-out looked finished at ~60% and then sat there until the clip lifted.
      stack.animate(
        [{ clipPath: `circle(0px at ${p.x}px ${p.y}px)` }, { clipPath: `circle(${r}px at ${p.x}px ${p.y}px)` }],
        { duration: OPEN_MS, easing: EASE_IN_OUT },
      );
    }
    stack.querySelectorAll('.ticket-fade').forEach((el) =>
      el.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], {
        duration: 220,
        delay: OPEN_MS * 0.4,
        easing: EASE_OUT,
        fill: 'backwards',
      }),
    );
    // Runs once on open; later row changes must not replay the entrance.
  }, []);

  // History entry so the system back gesture closes the ticket instead of leaving the app.
  useEffect(() => {
    if (!history.state?.[HISTORY_KEY]) history.pushState({ [HISTORY_KEY]: true }, '');
    const onPop = () => animateClose();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && back();
    window.addEventListener('popstate', onPop);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('popstate', onPop);
      window.removeEventListener('keydown', onKey);
    };
  }, [animateClose, back]);

  // Everything got filtered away underneath us: nothing left to show.
  useEffect(() => {
    if (rows.length === 0) back();
  }, [rows.length, back]);

  const scrollTo = (i: number) => {
    const stack = stackRef.current;
    if (stack) stack.scrollTo({ top: i * stack.clientHeight, behavior: 'smooth' });
  };

  // After a skip, the ticket that slid into place fades up so the swap reads as one motion.
  useLayoutEffect(() => {
    const stack = stackRef.current;
    if (!stack || arrived.current === null || prefersReducedMotion()) return;
    arrived.current = null;
    const now = stack.querySelectorAll('.ticket')[Math.round(stack.scrollTop / stack.clientHeight)];
    now?.querySelectorAll('.ticket-fade').forEach((el) =>
      el.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], {
        duration: 200,
        easing: EASE_OUT,
      }),
    );
  }, [gone]);

  const skip = (row: Row) => {
    const tell = () => send({ type: 'feedback', item_id: row.id, kind: 'skip' });
    if (rows.length === 1) {
      tell();
      back();
      return;
    }
    // Hide it here first, then tell the server: the swap never waits on a round trip,
    // and the server's updated board can't cut the fade short.
    const remove = () => {
      arrived.current = row.id;
      setGone((g) => [...g, row.id]);
      tell();
    };
    const ticket = stackRef.current?.querySelector(`[data-ticket-id="${CSS.escape(row.id)}"]`);
    if (!ticket || prefersReducedMotion()) {
      remove();
      return;
    }
    const fades = [...ticket.querySelectorAll('.ticket-fade')].map((el) =>
      el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: SKIP_FADE_MS, easing: 'ease-out', fill: 'forwards' }),
    );
    void Promise.all(fades.map(whenDone)).then(remove);
  };

  return (
    <>
    {/* Desktop: clicking the dimmed board around the panel closes it, instead of reaching the cards below */}
    <div className="ticket-backdrop" aria-hidden="true" onClick={back} />
    <div
      ref={stackRef}
      className="ticket-stack"
      role="dialog"
      aria-modal="true"
      aria-label="Departure tickets"
    >
      {rows.map((row, i) => (
        <Ticket
          key={row.id}
          row={row}
          radioAudio={row.id === open.id ? open.radioAudio : undefined}
          next={rows[i + 1] ?? null}
          nowMs={nowMs}
          student={state.vybe.student}
          liked={state.liked.includes(row.id)}
          onBack={back}
          onNext={() => scrollTo(i + 1)}
          onLike={() => {
            if (!state.liked.includes(row.id)) send({ type: 'feedback', item_id: row.id, kind: 'like' });
            dispatch({ type: 'toggle_like', id: row.id });
          }}
          onSkip={() => skip(row)}
        />
      ))}
    </div>
    </>
  );
}
