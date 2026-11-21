import type { RoomResume } from '../contract';
import { EMPTY_VYBE, isSpecificInterest, type Vybe } from './vybe';

const KEY = 'vybe:v1';
const ROOM_KEY = 'vybe:meetup';

export interface Saved {
  vybe: Vybe;
  liked: string[];
  onboarded: boolean;
}

/** `?reset` in the URL wipes the saved session and starts from the start screen. */
function consumeResetParam(): void {
  const url = new URL(location.href);
  if (!url.searchParams.has('reset')) return;
  try {
    localStorage.removeItem(KEY);
    sessionStorage.removeItem(ROOM_KEY);
  } catch {
    // nothing saved to clear
  }
  url.searchParams.delete('reset');
  history.replaceState(null, '', url);
}

export function loadSaved(): Saved {
  const fallback: Saved = { vybe: EMPTY_VYBE, liked: [], onboarded: false };
  consumeResetParam();
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<Saved>;
    return {
      vybe: { ...EMPTY_VYBE, ...parsed.vybe },
      liked: Array.isArray(parsed.liked) ? parsed.liked.filter((id) => typeof id === 'string') : [],
      onboarded: parsed.onboarded === true,
    };
  } catch {
    return fallback;
  }
}

export function save(data: Saved): void {
  try {
    const vybe = {
      ...data.vybe,
      requested: undefined,
      into: data.vybe.into.filter((tag) => !isSpecificInterest(tag)),
      notInto: data.vybe.notInto.filter((tag) => !isSpecificInterest(tag)),
    };
    localStorage.setItem(KEY, JSON.stringify({ ...data, vybe }));
  } catch {
    // Private mode or storage full: the app still works, it just won't remember.
  }
}

interface RoomHistory {
  active: RoomResume | null;
  recent: RoomResume[];
}

function roomHistory(): RoomHistory {
  try {
    return JSON.parse(sessionStorage.getItem(ROOM_KEY) ?? 'null') ?? { active: null, recent: [] };
  } catch {
    return { active: null, recent: [] };
  }
}

export function readRoom(): RoomResume | null {
  const { active, recent } = roomHistory();
  const invite = inviteFromUrl();
  return invite === null ? active : recent.find((room) => room.invite === invite) ?? null;
}

export function saveRoom(room: RoomResume | null, remove?: RoomResume | null): void {
  try {
    const { recent } = roomHistory();
    const next = recent.filter((previous) =>
      previous.credential !== remove?.credential && previous.invite !== room?.invite);
    if (room?.invite) next.push(room);
    sessionStorage.setItem(ROOM_KEY, JSON.stringify({ active: room, recent: next.slice(-10) }));
  } catch {
    // The connection can still resume with the in-memory credential.
  }
}

export function inviteFromUrl(): string | null {
  return new URLSearchParams(location.hash.slice(1)).get('invite');
}

export function clearInvite(): void {
  if (inviteFromUrl() === null) return;
  const url = new URL(location.href);
  url.hash = '';
  history.replaceState(null, '', url);
}
