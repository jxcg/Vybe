import { EMPTY_VYBE, type Vybe } from './vybe';

const KEY = 'vybe:v1';

export interface Saved {
  vybe: Vybe;
  room: string | null;
  onboarded: boolean;
}

/** `?reset` in the URL wipes the saved session and starts from the start screen. */
function consumeResetParam(): void {
  const url = new URL(location.href);
  if (!url.searchParams.has('reset')) return;
  try {
    localStorage.removeItem(KEY);
  } catch {
    // nothing saved to clear
  }
  url.searchParams.delete('reset');
  history.replaceState(null, '', url);
}

export function loadSaved(): Saved {
  const fallback: Saved = { vybe: EMPTY_VYBE, room: null, onboarded: false };
  consumeResetParam();
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<Saved>;
    return {
      vybe: { ...EMPTY_VYBE, ...parsed.vybe },
      room: parsed.room ?? null,
      onboarded: parsed.onboarded === true,
    };
  } catch {
    return fallback;
  }
}

export function save(data: Saved): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(data));
  } catch {
    // Private mode or storage full: the app still works, it just won't remember.
  }
}
