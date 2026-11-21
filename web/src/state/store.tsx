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
import type { BoardMsg, ClientMessage, ServerMessage } from '../contract';
import { createSocket, type ConnStatus, type VybeSocket } from '../net/socket';
import { loadSaved, save } from '../lib/storage';
import { mergeChips, toPrefs, type Vybe } from '../lib/vybe';

export type Screen = 'start' | 'loading' | 'board';

/** The ticket being viewed and the screen point it opened from (the colour expands from there). */
export interface OpenTicket {
  id: string;
  x: number;
  y: number;
}

export interface Toast {
  id: number;
  text: string;
}

export interface State {
  conn: ConnStatus;
  room: string | null;
  you: string | null;
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
  | { type: 'go'; screen: Screen }
  | { type: 'clear_transcript' }
  | { type: 'dismiss_toast'; id: number }
  | { type: 'open_ticket'; ticket: OpenTicket }
  | { type: 'close_ticket' }
  | { type: 'toggle_like'; id: string };

function init(): State {
  const saved = loadSaved();
  return {
    conn: 'connecting',
    room: saved.room,
    you: null,
    board: null,
    boardAt: 0,
    screen: saved.onboarded ? 'loading' : 'start',
    onboarded: saved.onboarded,
    vybe: saved.vybe,
    transcript: '',
    chipsSeq: 0,
    toasts: [],
    ticket: null,
    liked: [],
  };
}

let toastId = 0;

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'conn':
      return { ...state, conn: action.status };
    case 'set_vybe':
      return { ...state, vybe: action.vybe };
    case 'go':
      return {
        ...state,
        screen: action.screen,
        onboarded: state.onboarded || action.screen !== 'start',
      };
    case 'clear_transcript':
      return { ...state, transcript: '' };
    case 'dismiss_toast':
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.id) };
    case 'open_ticket':
      return { ...state, ticket: action.ticket };
    case 'close_ticket':
      return { ...state, ticket: null };
    case 'toggle_like':
      return {
        ...state,
        liked: state.liked.includes(action.id)
          ? state.liked.filter((id) => id !== action.id)
          : [...state.liked, action.id],
      };
    case 'server': {
      const { msg } = action;
      switch (msg.type) {
        case 'joined':
          return { ...state, room: msg.room, you: msg.you };
        case 'board':
          return { ...state, board: msg, boardAt: action.at };
        case 'transcript':
          return { ...state, transcript: msg.text };
        case 'note':
          return { ...state, toasts: [...state.toasts, { id: ++toastId, text: msg.text }] };
        case 'chips':
          return { ...state, vybe: mergeChips(state.vybe, msg), chipsSeq: state.chipsSeq + 1 };
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
  /** Sends join + current prefs once per connection. */
  join: () => void;
}

const StoreContext = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, init);
  const socketRef = useRef<VybeSocket | null>(null);
  const joinedRef = useRef(false);
  const latest = useRef(state);
  latest.current = state;

  const send = useCallback((msg: ClientMessage) => socketRef.current?.send(msg), []);

  const join = useCallback(() => {
    if (joinedRef.current) return;
    joinedRef.current = true;
    const { room, vybe } = latest.current;
    send({ type: 'join', room });
    send({ type: 'prefs', ...toPrefs(vybe) });
  }, [send]);

  useEffect(() => {
    const socket = createSocket();
    socketRef.current = socket;
    joinedRef.current = false;
    const offMsg = socket.subscribe((msg) => dispatch({ type: 'server', msg, at: Date.now() }));
    const offStatus = socket.onStatus((status) => dispatch({ type: 'conn', status }));
    if (latest.current.onboarded) join();
    return () => {
      offMsg();
      offStatus();
      socket.close();
      socketRef.current = null;
    };
  }, [join]);

  // Every change to the vybe goes to the server (and survives a reload).
  const { vybe, room, onboarded } = state;
  useEffect(() => {
    send({ type: 'prefs', ...toPrefs(vybe) });
  }, [vybe, send]);

  useEffect(() => {
    save({ vybe, room, onboarded });
  }, [vybe, room, onboarded]);

  return (
    <StoreContext.Provider value={{ state, dispatch, send, join }}>
      {children}
    </StoreContext.Provider>
  );
}

export function useStore(): Store {
  const store = useContext(StoreContext);
  if (!store) throw new Error('useStore must be used inside <StoreProvider>');
  return store;
}
