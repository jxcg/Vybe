import { useStore } from '../state/store';
import './ReconnectBanner.css';

/** Thin strip while the socket is down. The last board stays on screen underneath. */
export function ReconnectBanner() {
  const { state } = useStore();
  if (state.conn === 'open') return null;
  return (
    <div className="reconnect" role="status">
      {state.conn === 'connecting' ? 'Connecting…' : 'Reconnecting…'}
    </div>
  );
}
