import type { BoardMsg, Budget, ChipsMsg, ClientMessage, Pick, Prefs, Row, ServerMessage, Status } from '../contract';
import { MOCK_ITEMS, type MockItem } from '../mock/items';
import { londonWallTime, MINUTE } from '../lib/time';
import type { ConnStatus, VybeSocket } from './socket';

const TICK_MS = 250;
const BOARD_MS = 2000;
const LEAVE_BUFFER_MIN = 5;
const DEPARTED_KEEP_MIN = 10;
const PICK_SLOTS: Pick[] = ['best', 'runner_up', 'wildcard'];

const DEFAULT_PREFS: Prefs = {
  budget: 999,
  student: false,
  adult: true,
  include: [],
  exclude: [],
  company: 1,
};

const MOCK_SENTENCE = 'Me and two mates, want a laugh, nothing over a tenner.';
const MOCK_SENTENCE_CHIPS: ChipsMsg = { type: 'chips', include: ['a laugh'], exclude: [], budget: 10, company: 3 };
const WORD_MS = 280;
const THINK_MS = 700;

/** How the mock reads "not into" tags against its items. */
const EXCLUDES: Record<string, (item: MockItem) => boolean> = {
  outdoors: (i) => i.outdoor,
  'loud music': (i) => i.category === 'music' || i.id === 'booth-nine',
  'late nights': (i) => i.depart >= '22:00',
};

/** Tiny keyword reader standing in for the server's language model. */
function chipsFromText(text: string): ChipsMsg {
  const t = text.toLowerCase();
  const include: string[] = [];
  const exclude: string[] = [];
  const has = (...words: string[]) => words.some((w) => t.includes(w));
  if (has('laugh', 'comedy', 'funny')) include.push('a laugh');
  if (has('chill', 'relax', 'quiet')) include.push('chill');
  if (has('eat', 'food', 'hungry', 'dinner')) include.push('food');
  if (has('music', 'jazz', 'gig')) include.push('live music');
  if (has('active', 'bowling', 'ping')) include.push('active');
  if (has('art', 'gallery', 'culture')) include.push('culture');
  if (has('outdoor', 'outside')) exclude.push('outdoors');
  if (has('loud')) exclude.push('loud music');
  let budget: Budget | undefined;
  const amount = /(?:under|less than|max|over)\s*£?\s*(\d+)/.exec(t)?.[1];
  if (has('tenner', 'cheap', 'skint')) budget = 10;
  else if (amount) budget = Number(amount) <= 10 ? 10 : Number(amount) <= 20 ? 20 : 999;
  let company: number | undefined;
  const mates = /(one|two|three|four|\d) (?:mates|friends|people)/.exec(t)?.[1];
  if (mates) company = 1 + (['one', 'two', 'three', 'four'].indexOf(mates) + 1 || Number(mates));
  else if (has('on my own', 'just me', 'solo')) company = 1;
  return { type: 'chips', include, exclude, budget, company };
}

/**
 * In-browser stand-in for the server. This is the ONLY place on the client that computes statuses.
 */
export function createMockSocket(): VybeSocket {
  const listeners = new Set<(msg: ServerMessage) => void>();
  const day = new Date();
  const rainFrom = londonWallTime(day, '19:30').getTime();
  let clock = londonWallTime(day, '18:45').getTime();
  let prefs: Prefs = DEFAULT_PREFS;
  let intervals: number[] = [];
  let joined = false;
  const hidden = new Set<string>();
  let talkTimer: number | undefined;
  let spoken = 0;

  const emit = (msg: ServerMessage) => {
    setTimeout(() => listeners.forEach((cb) => cb(msg)), 0);
  };

  function matches(item: MockItem): boolean {
    if (item.your_price !== null && item.your_price > prefs.budget) return false;
    if (item.adult && !prefs.adult) return false;
    return !prefs.exclude.some((tag) => tag === item.category || EXCLUDES[tag]?.(item));
  }

  function toRow(item: MockItem, now: number): Row {
    const { depart, outdoor, adult, checked_min_ago, ...rest } = item;
    const departure = londonWallTime(day, depart).getTime();
    const leaveBy = departure - (item.walk_min + LEAVE_BUFFER_MIN) * MINUTE;
    const mins = (leaveBy - now) / MINUTE;
    let status: Status =
      mins >= 20 ? 'on_time' : mins >= 5 ? 'boarding' : mins >= 0 ? 'last_call' : 'departed';
    if (status !== 'departed' && outdoor && rainFrom <= departure) status = 'delayed_rain';
    return {
      ...rest,
      departure_time: new Date(departure).toISOString(),
      leave_by: new Date(leaveBy).toISOString(),
      status,
      checked_at: new Date(now - checked_min_ago * MINUTE).toISOString(),
    };
  }

  function assignPicks(rows: Row[]) {
    for (const r of rows) {
      if (r.pick && (r.status === 'departed' || r.status === 'delayed_rain')) r.pick = null;
    }
    const taken = new Set(rows.map((r) => r.pick));
    const spare = rows
      .filter((r) => !r.pick && r.status !== 'departed' && r.status !== 'delayed_rain')
      .sort((a, b) => b.score - a.score);
    for (const slot of PICK_SLOTS) {
      if (taken.has(slot)) continue;
      const next = spare.shift();
      if (next) next.pick = slot;
    }
  }

  function board(): BoardMsg {
    const rows = MOCK_ITEMS.filter((item) => !hidden.has(item.id) && matches(item))
      .map((item) => toRow(item, clock))
      .filter((r) => Date.parse(r.leave_by) > clock - DEPARTED_KEEP_MIN * MINUTE)
      .sort((a, b) => Date.parse(a.leave_by) - Date.parse(b.leave_by));
    assignPicks(rows);
    return {
      type: 'board',
      now: new Date(clock).toISOString(),
      area: 'London Bridge',
      weather: { summary: 'Light rain', rain_from: new Date(rainFrom).toISOString() },
      count: rows.filter((r) => r.status !== 'departed' && r.status !== 'cancelled').length,
      members: ['You'],
      rows,
      boarded: {},
      decision: null,
    };
  }

  function start() {
    if (intervals.length) return;
    let last = performance.now();
    intervals = [
      window.setInterval(() => {
        const t = performance.now();
        clock += t - last;
        last = t;
      }, TICK_MS),
      window.setInterval(() => emit(board()), BOARD_MS),
    ];
  }

  return {
    send(msg: ClientMessage) {
      switch (msg.type) {
        case 'join':
          joined = true;
          emit({ type: 'joined', room: msg.room ?? 'mock-room', you: msg.name ?? 'You' });
          start();
          emit(board());
          break;
        case 'prefs': {
          const { type, ...next } = msg;
          prefs = next;
          if (joined) emit(board());
          break;
        }
        case 'talk_start': {
          const words = MOCK_SENTENCE.split(' ');
          spoken = 0;
          clearInterval(talkTimer);
          talkTimer = window.setInterval(() => {
            if (spoken >= words.length) return;
            spoken += 1;
            emit({ type: 'transcript', text: words.slice(0, spoken).join(' '), final: false });
          }, WORD_MS);
          break;
        }
        case 'talk_end':
          clearInterval(talkTimer);
          emit({ type: 'transcript', text: MOCK_SENTENCE, final: true });
          setTimeout(() => emit(MOCK_SENTENCE_CHIPS), THINK_MS);
          break;
        case 'feedback': {
          const item = MOCK_ITEMS.find((i) => i.id === msg.item_id);
          if (!item) break;
          if (msg.kind === 'skip') {
            hidden.add(item.id);
            emit({ type: 'note', text: `Hidden ${item.name}. We\u2019ll show fewer like it.` });
            emit(board());
          } else {
            emit({ type: 'note', text: `Saved ${item.name}` });
          }
          break;
        }
        case 'talk_text':
          setTimeout(() => emit(chipsFromText(msg.text)), THINK_MS);
          break;
        case 'time_travel':
          clock = Date.parse(msg.now);
          emit(board());
          break;
        case 'refresh_now':
          emit(board());
          break;
        default:
          break;
      }
    },
    subscribe(cb) {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    onStatus(cb: (status: ConnStatus) => void) {
      cb('open');
      return () => undefined;
    },
    close() {
      intervals.forEach(clearInterval);
      intervals = [];
      clearInterval(talkTimer);
      listeners.clear();
    },
  };
}
