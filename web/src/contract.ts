// Wire contract between the phone and the VYBE server. The server is the source of truth.

export type Category = 'comedy' | 'games' | 'food' | 'music' | 'culture' | 'bar' | 'other';

export type Status =
  | 'on_time'
  | 'boarding'
  | 'last_call'
  | 'departed'
  | 'delayed_rain'
  | 'cancelled';

export type DepartureLabel =
  | 'Starts'
  | 'Deal ends'
  | 'Last entry'
  | 'Kitchen closes'
  | 'Open till'
  | 'Open 24 hours';

export type Pick = 'best' | 'runner_up' | 'wildcard';

export type Budget = 10 | 20 | 999;

export interface VenueColors {
  deep: string;
  soft: string;
  light: string;
}

export interface Reason {
  /** lucide icon name, e.g. "Footprints" */
  icon: string;
  text: string;
}

export interface Row {
  id: string;
  name: string;
  venue: string;
  category: Category;
  /** What people browse by: Food, Drinks, Entertainment, Culture, Outdoors (server extension) */
  group?: string;
  /** Server extension. false = walk-in place with no set time (show "Open till …", not a big time). */
  timed?: boolean;
  /** Server extension. true = shows, gigs, comedy, cinema: book ahead. */
  needs_booking?: boolean;
  departure_time: string;
  departure_label: DepartureLabel;
  status: Status;
  leave_by: string;
  walk_min: number;
  your_price: number | null;
  /** Server extension: 1–3, shown as £ / ££ / £££ when there's no exact price */
  price_level?: number;
  price_unknown?: boolean;
  /** Server extension: pricier than the user's budget (kept as an option, ranked lower) */
  over_budget?: boolean;
  was_price: number | null;
  /** 0–10 */
  score: number;
  pick: Pick | null;
  /** at most 3 */
  reasons: Reason[];
  photo_url: string | null;
  photo_credit?: string | null;
  photo_fade_start?: number | null;
  google_place_photo?: boolean;
  colors: VenueColors | null;
  pitch: string;
  voiceover_url: string | null;
  booking_url: string | null;
  rating: number | null;
  lat: number;
  lng: number;
  source_url: string | null;
  checked_at: string;
}

export interface Weather {
  summary: string;
  rain_from: string | null;
}

export interface Plan {
  leave_in_min: number;
  walk_min: number;
}

export interface Decision {
  item_id: string;
  by: string;
  plan: Plan;
}

// ── Phone → server ──────────────────────────────────────────────

export interface JoinMsg {
  type: 'join';
  room: string | null;
  name?: string;
}

export interface PrefsMsg {
  type: 'prefs';
  budget: Budget;
  student: boolean;
  adult: boolean;
  include: string[];
  exclude: string[];
  /** Concrete, session-only searches in the current feed. */
  requested?: string[];
  /** people including you */
  company: number;
  liked?: string[];
  /** Server extension: age range ("under18", "18-21", "22-25", "26-35", "36+") and vibe ("chill" | "lively") */
  age?: string | null;
  vibe?: string | null;
}

export type TalkPurpose = 'mood' | 'command' | 'reason';

export interface TalkStartMsg {
  type: 'talk_start';
  purpose: TalkPurpose;
  item_id?: string;
}

export interface TalkEndMsg {
  type: 'talk_end';
}

/** Typed alternative to talk_start/talk_end; the server answers with `chips`. */
export interface TalkTextMsg {
  type: 'talk_text';
  text: string;
}

export interface FeedbackMsg {
  type: 'feedback';
  item_id: string;
  kind: 'like' | 'unlike' | 'skip';
}

export interface BoardOnMsg {
  type: 'board_on';
  item_id: string | null;
}

/** Server extension: show only one group (Food, Drinks, Entertainment, Culture, Outdoors), or all. */
export interface ShowMsg {
  type: 'show';
  group: string | null;
}

export interface TimeTravelMsg {
  type: 'time_travel';
  now: string;
}

export interface RefreshNowMsg {
  type: 'refresh_now';
}

export interface RoomCredential {
  invite: string;
  credential: string;
}

export interface RoomResume {
  invite: string | null;
  credential: string;
}

export interface RoomEntry {
  type: 'room_create' | 'room_join';
  invite?: string;
  name: string;
  prefs: Prefs;
  liked: string[];
}

type RoomCommand =
  | (RoomEntry & { credential: string })
  | { type: 'room_check'; invite: string }
  | ({ type: 'room_resume' } & RoomResume)
  | { type: 'room_prefs'; prefs: Prefs }
  | { type: 'room_leave' };

export type ClientMessage =
  | JoinMsg
  | PrefsMsg
  | TalkStartMsg
  | TalkEndMsg
  | TalkTextMsg
  | FeedbackMsg
  | BoardOnMsg
  | TimeTravelMsg
  | RefreshNowMsg
  | ShowMsg
  | RoomCommand;

export type Prefs = Omit<PrefsMsg, 'type'>;

// ── Server → phone ──────────────────────────────────────────────

export interface JoinedMsg {
  type: 'joined';
  room: string;
  you: string;
}

export interface BoardMsg {
  type: 'board';
  now: string;
  area: string;
  weather: Weather;
  count: number;
  members: string[];
  rows: Row[];
  boarded: Record<string, string[]>;
  decision: Decision | null;
  /** Server extension: places per group before any filter, and the group being shown. */
  groups?: Record<string, number>;
  group?: string | null;
}

export interface TranscriptMsg {
  type: 'transcript';
  text: string;
  final: boolean;
}

export interface ChipsMsg {
  type: 'chips';
  include: string[];
  exclude: string[];
  budget?: Budget;
  student?: boolean;
  company?: number;
}

export interface NoteMsg {
  type: 'note';
  text: string;
}

export interface AnnounceMsg {
  type: 'announce';
  item_id: string;
  kind: 'boarding' | 'last_call' | 'doors';
  url: string;
  caption: string;
}

export interface DecisionMsg extends Decision {
  type: 'decision';
}

export interface RoomJoined extends RoomCredential {
  type: 'room_joined';
  prefs: Prefs;
  liked: string[];
}

export type ServerMessage =
  | JoinedMsg
  | BoardMsg
  | TranscriptMsg
  | ChipsMsg
  | NoteMsg
  | AnnounceMsg
  | DecisionMsg
  | RoomJoined
  | { type: 'room_ready'; area: string }
  | { type: 'room_error'; message: string }
  | { type: 'room_left' };
