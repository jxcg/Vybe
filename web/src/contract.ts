// Wire contract between the phone and the VYBE server. The server is the source of truth.

export type Category = 'comedy' | 'games' | 'food' | 'music' | 'culture' | 'bar' | 'other';

export type Status =
  | 'on_time'
  | 'boarding'
  | 'last_call'
  | 'departed'
  | 'delayed_rain'
  | 'cancelled';

export type DepartureLabel = 'Starts' | 'Deal ends' | 'Last entry' | 'Kitchen closes';

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
  departure_time: string;
  departure_label: DepartureLabel;
  status: Status;
  leave_by: string;
  walk_min: number;
  your_price: number | null;
  was_price: number | null;
  /** 0–10 */
  score: number;
  pick: Pick | null;
  /** at most 3 */
  reasons: Reason[];
  photo_url: string | null;
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
  /** people including you */
  company: number;
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
  kind: 'like' | 'skip';
}

export interface BoardOnMsg {
  type: 'board_on';
  item_id: string | null;
}

export interface TimeTravelMsg {
  type: 'time_travel';
  now: string;
}

export interface RefreshNowMsg {
  type: 'refresh_now';
}

export type ClientMessage =
  | JoinMsg
  | PrefsMsg
  | TalkStartMsg
  | TalkEndMsg
  | TalkTextMsg
  | FeedbackMsg
  | BoardOnMsg
  | TimeTravelMsg
  | RefreshNowMsg;

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

export type ServerMessage =
  | JoinedMsg
  | BoardMsg
  | TranscriptMsg
  | ChipsMsg
  | NoteMsg
  | AnnounceMsg
  | DecisionMsg;
