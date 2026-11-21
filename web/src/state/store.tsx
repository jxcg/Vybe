import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useRef,
  type Dispatch,
  type ReactNode,
} from 'react';
import type { BoardMsg, ClientMessage, RoomCredential, RoomEntry, RoomResume, ServerMessage } from '../contract';
import { createSocket, type ConnStatus, type VybeSocket } from '../net/socket';
import { clearInvite, inviteFromUrl, loadSaved, readRoom, save, saveRoom } from '../lib/storage';
import { fromPrefs, mergeChips, toPrefs, updatePersonal, type Vybe } from '../lib/vybe';

export type Screen = 'start' | 'loading' | 'board' | 'invite';

/** The ticket being viewed and the screen point it opened from (the colour expands from there). */
export interface OpenTicket {
  id: string;
  x: number;
  y: number;
  radioAudio?: HTMLAudioElement;
}

export interface Toast {
  id: number;
  text: string;
}

export interface State {
  conn: ConnStatus;
  shared: RoomCredential | null;
  roomConnecting: boolean;
  invite: string | null;
  inviteArea: string | null;
  roomError: string | null;
  soloVybe: Vybe;
  personal: Vybe;
  soloLiked: string[];
  board: BoardMsg | null;
  /** wall-clock ms when the last board arrived; lets the UI advance the server's `now` locally */
  boardAt: number;
  screen: Screen;
  /** true once the user has left the start screen at least once */
  onboarded: boolean;
  vybe: Vybe;
  transcript: string;
  /** bumps on every `chips` message so screens can react to "the server answered" */
  chipsSeq: number;
  toasts: Toast[];
  ticket: OpenTicket | null;
  /** rows the user bookmarked this session */
  liked: string[];
}

export type Action =
  | { type: 'server'; msg: ServerMessage; at: number }
  | { type: 'conn'; status: ConnStatus }
  | { type: 'set_vybe'; vybe: Vybe }
  | { type: 'reset_filters'; vybe: Vybe }
  | { type: 'go'; screen: Screen }
  | { type: 'clear_transcript' }
  | { type: 'dismiss_toast'; id: number }
  | { type: 'open_ticket'; ticket: OpenTicket }
  | { type: 'close_ticket' }
  | { type: 'toggle_like'; id: string }
  | { type: 'room_connecting' }
  | { type: 'dismiss_invite' }
  | { type: 'clear_room_error' };

function init(): State {
  const saved = loadSaved();
  const invite = inviteFromUrl();
  const room = readRoom();
  const resume = room && (invite === null || invite === room.invite) ? room : null;
  return {
    conn: 'connecting',
    shared: resume && resume.invite !== null ? { ...resume, invite: resume.invite } : null,
    roomConnecting: resume !== null,
    invite,
    inviteArea: null,
    roomError: null,
    soloVybe: saved.vybe,
    personal: saved.vybe,
    soloLiked: saved.liked,
    board: null,
    boardAt: 0,
    screen: resume ? 'board' : invite !== null ? 'invite' : saved.onboarded ? 'loading' : 'start',
    onboarded: saved.onboarded,
    vybe: saved.vybe,
    transcript: '',
    chipsSeq: 0,
    toasts: [],
    ticket: null,
    liked: saved.liked,
  };
}

let toastId = 0;

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'conn':
      return { ...state, conn: action.status, roomConnecting: state.roomConnecting ||
        (action.status === 'reconnecting' && state.shared !== null) };
    case 'room_connecting':
      return { ...state, roomConnecting: true, roomError: null };
    case 'set_vybe':
      return state.shared ? { ...state, vybe: action.vybe } : {
        ...state, vybe: action.vybe, soloVybe: action.vybe,
        personal: updatePersonal(state.personal, state.vybe, action.vybe),
      };
    case 'reset_filters':
      return {
        ...state, vybe: action.vybe, soloVybe: state.shared ? state.soloVybe : action.vybe,
        transcript: '',
      };
    case 'go':
      return {
        ...state,
        screen: action.screen,
        onboarded: state.onboarded || (!state.shared && action.screen !== 'start'),
      };
    case 'clear_transcript':
      return { ...state, transcript: '' };
    case 'dismiss_toast':
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.id) };
    case 'open_ticket':
      return { ...state, ticket: action.ticket };
    case 'close_ticket':
      return { ...state, ticket: null };
    case 'toggle_like': {
      const liked = state.liked.includes(action.id)
        ? state.liked.filter((id) => id !== action.id)
        : [...state.liked, action.id];
      return { ...state, liked, soloLiked: state.shared ? state.soloLiked : liked };
    }
    case 'dismiss_invite':
      return {
        ...state, invite: null, inviteArea: null, roomError: null, roomConnecting: false, board: null,
        screen: 'loading', onboarded: true,
      };
    case 'clear_room_error':
      return { ...state, roomError: null };
    case 'server': {
      const { msg } = action;
      switch (msg.type) {
        case 'room_joined':
          return {
            ...state, shared: { invite: msg.invite, credential: msg.credential }, invite: null,
            inviteArea: null, roomError: null, roomConnecting: false, board: null, screen: 'board', ticket: null,
            vybe: fromPrefs(msg.prefs), liked: msg.liked, transcript: '',
          };
        case 'room_ready':
          return { ...state, inviteArea: msg.area, roomError: null };
        case 'room_error':
          return state.shared || (state.roomConnecting && state.screen === 'board' && !state.board) ? {
            ...state, shared: null, board: null, ticket: null, screen: 'invite', invite: null,
            roomError: msg.message, roomConnecting: false, vybe: state.soloVybe, liked: state.soloLiked, transcript: '',
          } : { ...state, roomError: msg.message, roomConnecting: false };
        case 'room_left':
          return {
            ...state, shared: null, vybe: state.soloVybe, liked: state.soloLiked,
            board: null, screen: 'board', onboarded: true, ticket: null, transcript: '',
          };
        case 'board':
          return { ...state, board: msg, boardAt: action.at };
        case 'transcript':
          return { ...state, transcript: msg.text };
        case 'note':
          return { ...state, toasts: [...state.toasts, { id: ++toastId, text: msg.text }] };
        case 'chips': {
          const vybe = mergeChips(state.vybe, msg);
          return { ...state, vybe, soloVybe: state.shared ? state.soloVybe : vybe, chipsSeq: state.chipsSeq + 1 };
        }
        default:
          return state;
      }
    }
  }
}

interface Store {
  state: State;
  dispatch: Dispatch<Action>;
  send: (msg: ClientMessage) => void;
  sendAudio: (frame: ArrayBuffer) => void;
  join: (vybe?: Vybe) => void;
  dismissInvite: () => void;
  enterRoom: (entry: RoomEntry) => void;
}

const StoreContext = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, init);
  const socketRef = useRef<VybeSocket | null>(null);
  const started = useRef(state.onboarded);
  const soloJoined = useRef(false);
  const resume = useRef<RoomResume | null>(state.roomConnecting ? readRoom() : null);
  const pendingEntry = useRef<(RoomEntry & { credential: string }) | null>(null);
  const latest = useRef(state);
  latest.current = state;

  const send = useCallback((msg: ClientMessage) => socketRef.current?.send(msg), []);
  const sendAudio = useCallback((frame: ArrayBuffer) => socketRef.current?.sendAudio(frame), []);

  const joinSolo = useCallback((vybe: Vybe, liked: string[]) => {
    if (soloJoined.current) return;
    soloJoined.current = true;
    send({ type: 'prefs', ...toPrefs(vybe), liked });
    send({ type: 'join', room: null });
  }, [send]);

  const join = useCallback((vybe = latest.current.vybe) => {
    if (latest.current.shared) {
      if (latest.current.roomConnecting) return;
      send({ type: 'room_prefs', prefs: toPrefs(vybe) });
      return;
    }
    started.current = true;
    if (latest.current.conn === 'open') joinSolo(vybe, latest.current.soloLiked);
  }, [joinSolo, send]);

  const enterRoom = useCallback((entry: RoomEntry) => {
    if (pendingEntry.current || latest.current.conn !== 'open') return;
    const credential = Array.from(crypto.getRandomValues(new Uint8Array(32)),
      (byte) => byte.toString(16).padStart(2, '0')).join('');
    resume.current = { invite: entry.invite ?? null, credential };
    pendingEntry.current = { ...entry, credential };
    saveRoom(resume.current);
    dispatch({ type: 'room_connecting' });
    send(pendingEntry.current);
  }, [send]);

  const dismissInvite = useCallback(() => {
    saveRoom(null, resume.current);
    resume.current = null;
    pendingEntry.current = null;
    clearInvite();
    dispatch({ type: 'dismiss_invite' });
    soloJoined.current = false;
    join(latest.current.soloVybe);
  }, [join]);

  useEffect(() => {
    const socket = createSocket();
    socketRef.current = socket;
    const offMsg = socket.subscribe((msg) => {
      if (msg.type === 'room_joined') {
        const shared = { invite: msg.invite, credential: msg.credential };
        resume.current = shared;
        pendingEntry.current = null;
        saveRoom(shared);
        clearInvite();
      } else if (msg.type === 'room_left' || (msg.type === 'room_error' && resume.current)) {
        saveRoom(null, resume.current);
        resume.current = null;
        pendingEntry.current = null;
      }
      if (msg.type === 'room_left') {
        started.current = true;
        soloJoined.current = true;
      }
      dispatch({ type: 'server', msg, at: Date.now() });
    });
    const offStatus = socket.onStatus((status) => {
      dispatch({ type: 'conn', status });
      if (status !== 'open') return;
      soloJoined.current = false;
      const current = latest.current;
      if (resume.current) {
        send({ type: 'prefs', ...toPrefs(current.soloVybe), liked: current.soloLiked });
        send(pendingEntry.current ?? { type: 'room_resume', ...resume.current });
      } else if (current.screen === 'invite') {
        send({ type: 'prefs', ...toPrefs(current.soloVybe), liked: current.soloLiked });
        if (current.invite !== null) send({ type: 'room_check', invite: current.invite });
      } else if (started.current) {
        joinSolo(current.soloVybe, current.soloLiked);
      } else {
        send({ type: 'prefs', ...toPrefs(current.soloVybe), liked: current.soloLiked });
      }
    });
    return () => {
      offMsg();
      offStatus();
      socket.close();
      socketRef.current = null;
    };
  }, [joinSolo, send]);

  const { soloVybe, soloLiked, personal, onboarded } = state;
  useEffect(() => {
    if (!state.shared) send({ type: 'prefs', ...toPrefs(soloVybe) });
  }, [soloVybe, state.shared, send]);

  useEffect(() => {
    save({ vybe: personal, liked: soloLiked, onboarded });
  }, [personal, soloLiked, onboarded]);

  return (
    <StoreContext.Provider value={{ state, dispatch, send, sendAudio, join, dismissInvite, enterRoom }}>
      {children}
    </StoreContext.Provider>
  );
}

export function useStore(): Store {
  const store = useContext(StoreContext);
  if (!store) throw new Error('useStore must be used inside <StoreProvider>');
  return store;
}
