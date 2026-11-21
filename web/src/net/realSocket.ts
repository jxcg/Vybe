import type { ClientMessage, JoinMsg, PrefsMsg, ServerMessage } from '../contract';
import type { ConnStatus, VybeSocket } from './socket';

const BASE_DELAY_MS = 500;
const MAX_DELAY_MS = 15_000;

function isServerMessage(data: unknown): data is ServerMessage {
  return typeof data === 'object' && data !== null && typeof (data as { type?: unknown }).type === 'string';
}

/**
 * WebSocket with exponential backoff. While disconnected, only the latest join + prefs are kept,
 * and they're replayed on every reconnect so the server can restore the session. Everything else
 * sent while offline (talk, feedback) is dropped: it would be stale by the time we're back.
 */
export function createRealSocket(url: string): VybeSocket {
  const listeners = new Set<(msg: ServerMessage) => void>();
  const statusListeners = new Set<(s: ConnStatus) => void>();
  let ws: WebSocket | null = null;
  let status: ConnStatus = 'connecting';
  let attempt = 0;
  let retryTimer: number | undefined;
  let closed = false;
  let lastJoin: JoinMsg | null = null;
  let lastPrefs: PrefsMsg | null = null;

  const setStatus = (next: ConnStatus) => {
    if (next === status) return;
    status = next;
    statusListeners.forEach((cb) => cb(next));
  };

  const rawSend = (msg: ClientMessage) => {
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  };

  const scheduleRetry = () => {
    if (closed) return;
    setStatus('reconnecting');
    const delay = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempt) * (0.75 + Math.random() * 0.5);
    attempt += 1;
    retryTimer = window.setTimeout(connect, delay);
  };

  function connect() {
    if (closed) return;
    const socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer';
    ws = socket;

    socket.onopen = () => {
      attempt = 0;
      setStatus('open');
      if (lastJoin) rawSend(lastJoin);
      if (lastPrefs) rawSend(lastPrefs);
    };

    socket.onmessage = (e: MessageEvent) => {
      if (typeof e.data !== 'string') return;
      let parsed: unknown;
      try {
        parsed = JSON.parse(e.data);
      } catch {
        return;
      }
      if (!isServerMessage(parsed)) return;
      // Rejoin the same room after a drop.
      if (parsed.type === 'joined' && lastJoin) lastJoin = { ...lastJoin, room: parsed.room };
      listeners.forEach((cb) => cb(parsed));
    };

    // onerror is always followed by onclose, which handles the retry.
    socket.onclose = () => {
      if (ws === socket) ws = null;
      scheduleRetry();
    };
  }

  connect();

  return {
    sendAudio(frame) {
      if (ws?.readyState === WebSocket.OPEN) ws.send(frame);
    },
    send(msg) {
      if (msg.type === 'join') lastJoin = msg;
      if (msg.type === 'prefs') lastPrefs = msg;
      rawSend(msg);
    },
    subscribe(cb) {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    onStatus(cb) {
      statusListeners.add(cb);
      cb(status);
      return () => statusListeners.delete(cb);
    },
    close() {
      closed = true;
      window.clearTimeout(retryTimer);
      listeners.clear();
      statusListeners.clear();
      ws?.close();
      ws = null;
    },
  };
}
