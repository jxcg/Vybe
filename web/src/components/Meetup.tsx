import { useState } from 'react';
import { Link2, Share2 } from 'lucide-react';
import { toPrefs } from '../lib/vybe';
import { useStore } from '../state/store';
import { RowSheet } from './RowSheet';
import { VybeCard, type RowKey } from './VybeCard';
import { Wordmark } from './Wordmark';
import './Meetup.css';

export function InviteScreen() {
  const { state, enterRoom, dismissInvite } = useStore();
  const [name, setName] = useState('');
  const [vybe, setVybe] = useState(state.personal);
  const [bringLikes, setBringLikes] = useState(false);
  const [sheet, setSheet] = useState<RowKey | null>(null);
  return (
    <main className="invite-screen">
      <Wordmark />
      <h1>{state.inviteArea ? `Join the plan in ${state.inviteArea}` : 'Vybe invite'}</h1>
      {state.roomError && <p role="alert">{state.roomError}</p>}
      {!state.inviteArea && !state.roomError && <p role="status">Checking your invite…</p>}
      {state.inviteArea && state.invite !== null && (
        <form onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim() || state.conn !== 'open' || state.invite === null) return;
          enterRoom({
            type: 'room_join', invite: state.invite, name: name.trim(),
            prefs: toPrefs(vybe), liked: bringLikes ? state.soloLiked : [],
          });
        }}>
          <label className="invite-name">
            Display name
            <input autoComplete="nickname" value={name} maxLength={32} required onChange={(e) => setName(e.target.value)} />
          </label>
          <p>Choose what to bring into this plan. Friends see your name and the shared board.</p>
          <VybeCard vybe={vybe} onChange={setVybe} onOpen={setSheet} />
          {state.soloLiked.length > 0 && (
            <label className="invite-likes">
              <input type="checkbox" checked={bringLikes} onChange={(e) => setBringLikes(e.target.checked)} />
              Include my saved likes
            </label>
          )}
          <button type="submit" className="meetup-primary" disabled={!name.trim() || state.conn !== 'open' || state.roomConnecting}>Join</button>
        </form>
      )}
      <button type="button" className="meetup-secondary" onClick={dismissInvite} disabled={state.roomConnecting}>Back to solo Vybe</button>
      {sheet && <RowSheet row={sheet} vybe={vybe} onCancel={() => setSheet(null)} onDone={(draft) => {
        setVybe(draft);
        setSheet(null);
      }} />}
    </main>
  );
}

export function Meetup({ showInvite }: { showInvite: boolean }) {
  const { state, send } = useStore();
  const [shareStatus, setShareStatus] = useState('');
  const { shared, board, conn } = state;
  if (!shared) return state.roomError && <p className="meetup" role="alert">{state.roomError}</p>;

  const url = new URL('/', location.origin);
  url.hash = new URLSearchParams({ invite: shared.invite }).toString();
  const link = url.toString();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setShareStatus('Link copied');
    } catch {
      setShareStatus('Select the link above to copy it.');
    }
  };

  const share = async () => {
    try {
      await navigator.share({ title: 'Join me on Vybe', url: link });
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) await copy();
    }
  };

  return (
    <section className="meetup" aria-label="Shared plan">
      <div className="meetup-summary">
        <p role="status">{board ? `In this plan · ${board.members.join(', ')}` : 'Opening your shared plan…'}</p>
        <button className="meetup-secondary" type="button" disabled={conn !== 'open' || state.roomConnecting} onClick={() => send({ type: 'room_leave' })}>
          Leave plan
        </button>
      </div>
      {showInvite && (
        <div className="meetup-invite">
          <label htmlFor="meetup-link">Invite link · valid for up to 4 hours</label>
          <input id="meetup-link" readOnly value={link} onFocus={(event) => event.currentTarget.select()} />
          <div className="meetup-actions">
            {typeof navigator.share === 'function' && (
              <button className="meetup-primary" type="button" onClick={() => void share()}>
                <Share2 size={16} aria-hidden="true" /> Share invite
              </button>
            )}
            <button className="meetup-secondary" type="button" onClick={() => void copy()}>
              <Link2 size={16} aria-hidden="true" /> Copy link
            </button>
            {shareStatus && <span role="status">{shareStatus}</span>}
          </div>
        </div>
      )}
    </section>
  );
}
