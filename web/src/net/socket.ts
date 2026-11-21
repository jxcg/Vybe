import type { ClientMessage, ServerMessage } from '../contract';
import { createMockSocket } from './mockSocket';
import { createRealSocket } from './realSocket';

export type ConnStatus = 'connecting' | 'open' | 'reconnecting';

/** Shared interface for the real WebSocket and the mock. */
export interface VybeSocket {
  send(msg: ClientMessage): void;
  /** Binary PCM16 16 kHz mic frames, sent only between talk_start and talk_end. */
  sendAudio(frame: ArrayBuffer): void;
  subscribe(cb: (msg: ServerMessage) => void): () => void;
  onStatus(cb: (status: ConnStatus) => void): () => void;
  close(): void;
}

export const isMock =
  new URLSearchParams(location.search).has('mock') || import.meta.env.VITE_MOCK === '1';

export function createSocket(): VybeSocket {
  if (isMock) return createMockSocket();
  const url = import.meta.env.VITE_VYBE_WS_URL?.trim() || `${location.origin.replace(/^http/, 'ws')}/ws`;
  return createRealSocket(url);
}
