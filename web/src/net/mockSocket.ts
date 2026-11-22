import type { BoardMsg, Budget, ChipsMsg, ClientMessage, Pick, Prefs, Row, ServerMessage, Status } from '../contract';
import { MOCK_ITEMS, type MockItem } from '../mock/items';
import { londonWallTime, MINUTE } from '../lib/time';
import type { ConnStatus, VybeSocket } from './socket';

const TICK_MS = 250;
const BOARD_MS = 2000;
const LEAVE_BUFFER_MIN = 5;
const DEPARTED_KEEP_MIN = 10;
const PICK_SLOTS: Pick[] = ['best', 'runner_up', 'wildcard'];

const MOCK_GROUPS: Record<string, string> = {
  food: 'Food', bar: 'Drinks', culture: 'Culture',
};

/** Mirrors the server: one matching interest narrows the board to its group until re-chosen. */
const INTEREST_GROUP: Record<string, string> = {
  food: 'Food', 'late night': 'Drinks', active: 'Entertainment',
  competitive: 'Entertainment', 'a laugh': 'Entertainment',
  'live music': 'Entertainment', culture: 'Culture', chill: 'Culture',
};

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
  clubs: (i) => i.category === 'bar' && i.adult,
  'loud music': (i) => i.category === 'music' || i.id === 'booth-nine',
  'late nights': (i) => i.depart >= '22:00',
  queues: (i) => i.walk_min >= 15,
};

/** Include chip → the mock categories it should lift (mirrors the server's tag families). */
const INCLUDE_CATEGORY: Record<string, string[]> = {
  'a laugh': ['comedy'],
  chill: ['culture'],
  food: ['food'],
  'live music': ['music'],
  active: ['games'],
  competitive: ['games'],
  culture: ['culture'],
  'late night': ['bar'],
};

const INCLUDE_KEYWORDS: [string[], string][] = [
  [['laugh', 'comedy', 'funny', 'stand-up', 'stand up', 'standup'], 'a laugh'],
  [['chill', 'relax', 'quiet', 'calm', 'low key'], 'chill'],
  [['eat', 'eating', 'food', 'hungry', 'dinner', 'lunch', 'brunch', 'pizza', 'burger', 'sushi',
    'ramen', 'curry', 'tacos', 'noodles', 'bite', 'dessert'], 'food'],
  [['music', 'jazz', 'gig', 'concert', 'band'], 'live music'],
  [['active', 'bowling', 'ping', 'darts', 'climbing', 'golf', 'karaoke', 'arcade', 'games'], 'active'],
  [['competitive', 'compete', 'tournament'], 'competitive'],
  [['art', 'gallery', 'museum', 'culture', 'exhibition', 'theatre'], 'culture'],
  [['dance', 'dancing', 'club', 'clubbing', 'rave', 'party', 'pint', 'beer', 'drink', 'drinking',
    'pub', 'bar', 'late'], 'late night'],
];

/** Tiny keyword reader standing in for the server's language model. */
export function chipsFromText(text: string): ChipsMsg {
  const t = text.toLowerCase();
  // Whole words only (plurals ok): "art" must not fire inside "party", "bar" not inside "embarrassed".
  const has = (...words: string[]) =>
    words.some((w) => new RegExp(`\\b${w.replace(/ /g, '\\s+')}(?:s)?\\b`).test(t));
  const include: string[] = [];
  for (const [words, chip] of INCLUDE_KEYWORDS) {
    if (has(...words) && !include.includes(chip)) include.push(chip);
  }
  if (has('competitive') && !include.includes('active')) include.push('active');
  const exclude: string[] = [];
  if (has('outdoor', 'outside') || /\braining\b/.test(t)) exclude.push('outdoors');
  if (has('loud', 'noisy') || /\bnot?\s*loud\b/.test(t)) exclude.push('loud music');
  if (/\bno clubs?\b|\bnot into clubs\b/.test(t)) exclude.push('clubs');
  if (/\bno late nights?\b/.test(t)) exclude.push('late nights');
  // "no clubs" shouldn't also mean wanting a late night (same rule as the server parser)
  if (exclude.includes('clubs') && !has('late')) {
    const i = include.indexOf('late night');
    if (i >= 0) include.splice(i, 1);
  }
  let budget: Budget | undefined;
  const amount = /(?:under|less than|max|over)\s*£?\s*(\d+)/.exec(t)?.[1];
  if (has('tenner', 'cheap', 'skint', 'fiver')) budget = 10;
  else if (amount) budget = Number(amount) <= 10 ? 10 : Number(amount) <= 20 ? 20 : 999;
  let company: number | undefined;
  const mates = /(one|two|three|four|\d) (?:mates|friends|people)/.exec(t)?.[1];
  if (mates) company = 1 + (['one', 'two', 'three', 'four'].indexOf(mates) + 1 || Number(mates));
  else if (has('on my own', 'just me', 'solo')) company = 1;
  else if (has('date', 'girlfriend', 'boyfriend', 'partner')) company = 2;
  const student = has('student', 'uni', 'university') ? true : undefined;
  return { type: 'chips', include, exclude, budget, company, student };
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
  let chosenGroup: string | null | undefined;
  let area = 'Demo board';
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
    // Into-tags lift a row the way the server's ranking does, so picks follow the filters.
    const intoHit = prefs.include.some((tag) => INCLUDE_CATEGORY[tag]?.includes(item.category));
    const studentDeal = prefs.student && item.was_price !== null;
    return {
      ...rest,
      score: Math.max(0, Math.min(10, item.score + (intoHit ? 2 : 0) + (studentDeal ? 0.5 : 0))),
      group: MOCK_GROUPS[item.category] ?? 'Entertainment',
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
    const allRows = MOCK_ITEMS.filter((item) => !hidden.has(item.id) && matches(item))
      .map((item) => toRow(item, clock))
      .filter((r) => Date.parse(r.leave_by) > clock - DEPARTED_KEEP_MIN * MINUTE)
      .sort((a, b) => Date.parse(a.leave_by) - Date.parse(b.leave_by));
    const groups: Record<string, number> = {};
    for (const row of allRows) {
      if (row.group && row.status !== 'departed' && row.status !== 'cancelled') {
        groups[row.group] = (groups[row.group] ?? 0) + 1;
      }
    }
    const group = chosenGroup === undefined
      ? prefs.include.map((tag) => INTEREST_GROUP[tag]).find((g) => Object.hasOwn(groups, g)) ?? null
      : chosenGroup;
    const rows = group ? allRows.filter((row) => row.group === group) : allRows;
    assignPicks(rows);
    return {
      type: 'board',
      now: new Date(clock).toISOString(),
      area,
      weather: { summary: 'Light rain', rain_from: new Date(rainFrom).toISOString() },
      count: rows.filter((r) => r.status !== 'departed' && r.status !== 'cancelled').length,
      members: ['You'],
      rows,
      boarded: {},
      decision: null,
      groups,
      group,
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
    sendAudio() {
      // the mock has no speech recognition; typed text works instead
    },
    send(msg: ClientMessage) {
      switch (msg.type) {
        case 'location':
          area = msg.label;
          if (joined) emit(board());
          break;
        case 'join':
          joined = true;
          emit({ type: 'joined', room: msg.room ?? 'mock-room', you: msg.name ?? 'You' });
          start();
          emit(board());
          break;
        case 'prefs': {
          const { type, ...next } = msg;
          if (JSON.stringify(prefs.include) !== JSON.stringify(next.include)) {
            chosenGroup = undefined; // a new interest re-opens the auto-narrowing
          }
          prefs = next;
          if (joined) emit(board());
          break;
        }
        case 'show':
          chosenGroup = msg.group;
          emit(board());
          break;
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
