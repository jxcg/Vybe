import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Keyboard } from 'lucide-react';
import { useStore } from '../state/store';
import { useTalk } from '../state/useTalk';
import { useKeyboardOpen } from '../lib/useKeyboardOpen';
import { fadeIn, fadeOutCopy, ghost, MORPH_MS, prefersReducedMotion, shapeOf, slideFrom } from '../lib/morph';
import { handoff } from '../lib/handoff';
import { isSpecificInterest, type Vybe } from '../lib/vybe';
import { FadePill } from './FadePill';
import { MicButton, type TalkPhase } from './MicButton';
import { RowSheet } from './RowSheet';
import { SentenceSlot } from './SentenceSlot';
import { TypeField } from './TypeField';
import { VybeCard, type RowKey } from './VybeCard';
import { ThemeToggle } from './ThemeToggle';
import { Wordmark } from './Wordmark';
import './StartScreen.css';

const TALK_MAX_MS = 15_000;
const THINKING_TIMEOUT_MS = 8_000;

const PHASE_LABEL: Record<TalkPhase, string> = {
  idle: 'Tap to talk',
  listening: 'Listening… tap when done',
  thinking: 'Got it…',
};

/** Phones go straight to the top layout in typing mode, so the keyboard never causes a second jump. */
const isTouch = window.matchMedia('(pointer: coarse)').matches;

export function StartScreen() {
  const { state, dispatch, send, setPlace, join } = useStore();
  const settings = state.onboarded || state.shared !== null;
  const [area, setArea] = useState(state.place?.label ?? '');
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState('');
  const areaRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<TalkPhase>('idle');
  const [typing, setTyping] = useState(false);
  const [sheet, setSheet] = useState<RowKey | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const micRef = useRef<HTMLButtonElement>(null);
  const voiceRef = useRef<HTMLDivElement>(null);
  const typeRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const morphing = useRef(false);
  const talkCap = useRef<number | undefined>(undefined);
  /** Set when the user asked to go while voice/typing was still being parsed: go once chips land. */
  const pendingGo = useRef(false);
  /** Last prompt sent to the server, so Enter on unchanged text doesn't send a duplicate. */
  const lastSentText = useRef('');
  const keyboardOpen = useKeyboardOpen();
  // Mic blocked or unavailable: fall back to typing (the hook shows a toast saying why)
  const talk = useTalk('mood', () => {
    setPhase('idle');
    switchMode(true);
  });

  // The server answered with chips: done thinking. A queued "go" now runs on the fresh filters.
  useEffect(() => {
    setPhase((p) => (p === 'thinking' ? 'idle' : p));
    if (pendingGo.current && go(undefined, true)) pendingGo.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.chipsSeq]);

  useEffect(() => {
    if (phase !== 'thinking') return;
    const t = window.setTimeout(() => setPhase('idle'), THINKING_TIMEOUT_MS);
    return () => window.clearTimeout(t);
  }, [phase]);

  useEffect(() => () => window.clearTimeout(talkCap.current), []);

  const endTalk = () => {
    window.clearTimeout(talkCap.current);
    talk.stop(); // sends the last audio, then talk_end
    setPhase('thinking');
  };

  const startTalk = () => {
    dispatch({ type: 'clear_transcript' });
    talk.start(); // talk_start, then streams PCM16 mic frames
    setPhase('listening');
    talkCap.current = window.setTimeout(endTalk, TALK_MAX_MS);
  };

  const onMic = () => (phase === 'listening' ? endTalk() : startTalk());

  /**
   * Voice <-> typing. The mic circle and the type bar are one shape: the lavender circle slides
   * into the bar's mic button while the bar grows out of it (and back). React switches layout
   * instantly; fixed "ghost" stand-ins do the flying, and the card glides to its new place.
   */
  const switchMode = (toTyping: boolean) => {
    if (morphing.current) return;
    if (toTyping && phase === 'listening') endTalk();
    if (!toTyping) inputRef.current?.blur();

    const form = formRef.current;
    const fromBar = toTyping ? micRef.current : form;
    const fromDot = toTyping ? micRef.current : form?.querySelector('.typefield-mic');
    const outgoing = toTyping ? voiceRef.current : typeRef.current;
    const cardTop = cardRef.current?.getBoundingClientRect().top;
    const animate = !prefersReducedMotion() && fromBar && fromDot && outgoing && cardTop !== undefined;
    const barStart = animate ? shapeOf(fromBar) : null;
    const dotStart = animate ? shapeOf(fromDot) : null;
    const icon = fromDot?.querySelector('svg');

    if (animate) {
      fadeOutCopy(outgoing, (copy) => {
        // The ghosts carry the shape; the copy only lets the surrounding text dissolve.
        copy.querySelectorAll<HTMLElement>('.mic, .typefield-mic').forEach((n) => (n.style.visibility = 'hidden'));
        const bar = copy.querySelector<HTMLElement>('.typefield');
        if (bar) Object.assign(bar.style, { background: 'transparent', borderColor: 'transparent' });
      });
    }

    flushSync(() => setTyping(toTyping));
    // Focus inside the tap so iOS raises the keyboard.
    if (toTyping) inputRef.current?.focus({ preventScroll: true });

    const nextForm = formRef.current;
    const toBar = toTyping ? nextForm : micRef.current;
    const toDot = toTyping ? nextForm?.querySelector('.typefield-mic') : micRef.current;
    const incoming = toTyping ? typeRef.current : voiceRef.current;
    if (!barStart || !dotStart || !toBar || !toDot || !incoming || cardTop === undefined) {
      if (incoming) fadeIn([incoming]);
      return;
    }

    const barEnd = shapeOf(toBar);
    const dotEnd = shapeOf(toDot);
    const hidden = toTyping ? toBar : toBar.parentElement!; // the whole .mic, ring included
    hidden.style.visibility = 'hidden';
    morphing.current = true;

    const flights = toTyping
      ? [
          // Bar materialises out of the circle, wearing its own colours throughout.
          ghost({ ...barStart, bg: barEnd.bg, border: barEnd.border }, barEnd, { opacity: [0, 1] }),
          ghost(dotStart, dotEnd, { icon }),
        ]
      : [
          ghost(barStart, { ...barEnd, bg: barStart.bg, border: barStart.border }, { opacity: [1, 0] }),
          ghost(dotStart, dotEnd, { icon }),
        ];

    if (cardRef.current?.getClientRects().length) slideFrom(cardRef.current, cardTop);
    if (!toTyping) {
      // "Tap to talk", the sentence and "Type instead" settle in behind the mic.
      fadeIn(incoming.querySelectorAll(':scope > :not(.mic)'), MORPH_MS * 0.35);
    }

    void Promise.all(flights).then(() => {
      hidden.style.visibility = '';
      if (toTyping) fadeIn(toBar.querySelectorAll('.typefield-icon, .typefield-input'), 0, 180);
      morphing.current = false;
    });
  };

  const setVybe = (vybe: Vybe) => dispatch({ type: 'set_vybe', vybe });

  const useMyLocation = () => {
    setLocationError('');
    if (!navigator.geolocation) {
      setLocationError('Browser location is unavailable. Enter an area or postcode instead.');
      areaRef.current?.focus();
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(({ coords }) => {
      setPlace({ type: 'location', lat: coords.latitude, lng: coords.longitude, label: 'Near you' });
      setLocating(false);
    }, () => {
      setLocationError('Couldn’t get your location. Allow location access or enter an area or postcode.');
      setLocating(false);
      areaRef.current?.focus();
    }, { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 });
  };

  const findArea = async () => {
    const query = area.trim();
    if (query.length < 2 || locating) return;
    setLocating(true);
    setLocationError('');
    try {
      const response = await fetch(`/api/geocode?${new URLSearchParams({ q: query })}`);
      if (!response.ok) throw new Error('lookup');
      const { lat, lng } = await response.json();
      if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) {
        throw new Error('coordinates');
      }
      setPlace({ type: 'location', lat, lng, label: query });
    } catch {
      setLocationError('Couldn’t find that place. Try another area or postcode.');
    } finally {
      setLocating(false);
    }
  };

  const go = (vybe?: Vybe, force = false): boolean => {
    if (state.shared && (state.conn !== 'open' || state.roomConnecting)) return false;
    // Solo boards need a session-only location: never fall back to a fixed area silently.
    if (!state.shared && (!state.place || locating)) {
      setLocationError('Choose your location before we find what’s nearby.');
      areaRef.current?.focus();
      return false;
    }
    if (!force && phase === 'thinking') return false;
    if (!force && phase === 'listening') {
      endTalk(); // chips arrive a moment later; pendingGo applies them instead of an earlier request
      pendingGo.current = true;
      return false;
    }
    if (vybe) setVybe(vybe);
    join(vybe);
    // First time in: the loading screen covers the wait, and the mic glides into its orb.
    // Coming back from settings: straight back to the board.
    if (state.board) {
      dispatch({ type: 'go', screen: 'board' });
      return true;
    }
    if (micRef.current) handoff.put('orb', shapeOf(micRef.current));
    dispatch({ type: 'go', screen: 'loading' });
    return true;
  };

  return (
    <div className={settings ? 'start' : 'start start--onboarding'}>
      <div className="start-body">
        <div className="start-top">
          <Wordmark size="lg" />
          <ThemeToggle />
        </div>
        <h1 className="start-title">{state.shared ? 'Change your plan preferences' : settings ? 'Change your vybe' : 'Let’s build your vybe.'}</h1>
        <p className="start-sub">
          Tell us what you{'\u2019'}re in the mood for. Just talk, we{'\u2019'}ll sort out the details.
        </p>

        <div className={`start-main${typing && (isTouch || keyboardOpen) ? ' start-main--top' : ''}`}>
          {typing ? (
            <div key="type" ref={typeRef} className="start-type">
              <TypeField
                inputRef={inputRef}
                formRef={formRef}
                onSend={(text, viaEnter) => {
                  if (state.conn !== 'open') return;
                  if (!viaEnter && phase === 'thinking') return; // don't stack debounced sends
                  // Enter on already-sent text arrives without a fresh send; still queue the go.
                  if (text !== lastSentText.current) {
                    lastSentText.current = text;
                    setPhase('thinking');
                    send({ type: 'talk_text', text });
                  }
                  // Enter means "go": open the board once the chips for this prompt arrive.
                  if (viaEnter) pendingGo.current = true;
                }}
                onVoice={() => switchMode(false)}
              />
            </div>
          ) : (
            <div key="voice" ref={voiceRef} className="start-voice">
              <MicButton phase={phase} onPress={onMic} buttonRef={micRef} />
              <p className="start-phase">{PHASE_LABEL[phase]}</p>
              <SentenceSlot text={state.transcript} />
              <button type="button" className="start-type-btn" onClick={() => switchMode(true)}>
                <Keyboard size={16} strokeWidth={2} aria-hidden="true" />
                Type instead
              </button>
            </div>
          )}

          <div ref={cardRef} className="start-card">
            {!state.shared && (
              <section className="start-location" aria-labelledby="location-title" aria-busy={locating}>
                <h2 id="location-title">Where are you?</h2>
                <p>Use your location or choose an area to explore. Only used for this session.</p>
                <button type="button" className="start-location-button" disabled={locating} onClick={useMyLocation}>
                  {locating ? 'Finding location…' : 'Use my location'}
                </button>
                <form onSubmit={(event) => { event.preventDefault(); void findArea(); }}>
                  <label htmlFor="location-area">Or enter an area or postcode</label>
                  <div className="start-location-search">
                    <input id="location-area" ref={areaRef} value={area} onChange={(event) => setArea(event.target.value)}
                      autoComplete="off" minLength={2} maxLength={100} required disabled={locating} />
                    <button type="submit" className="start-location-button" disabled={locating || area.trim().length < 2}>Find area</button>
                  </div>
                </form>
                {state.place && <p role="status">Using {state.place.label}</p>}
                {locationError && <p role="alert">{locationError}</p>}
              </section>
            )}
            <VybeCard vybe={state.vybe} onChange={setVybe} onOpen={setSheet} />
            <p className="start-hint">Tap any row to change it.</p>
          </div>
        </div>

      </div>

      {!(typing && keyboardOpen) && (
        <div className="start-footer">
          <FadePill
            label={phase === 'thinking' ? 'Applying filters…' : phase === 'listening'
              ? 'Finish recording' : settings ? 'Update board' : 'See what’s on'}
            disabled={phase === 'thinking' || locating}
            onClick={() => go()}
          />
          <button
            type="button"
            className="start-link"
            disabled={phase !== 'idle'}
            onClick={() => go({ ...state.vybe, requested: [], into: [], notInto: [], budget: 999 })}
          >
            Skip, show me everything
          </button>
        </div>
      )}

      {sheet && (
        <RowSheet
          row={sheet}
          vybe={state.vybe}
          onCancel={() => setSheet(null)}
          onDone={(vybe) => {
            const choseNewInterest = sheet === 'into' && vybe.into.some(
              (tag) => !isSpecificInterest(tag) && !state.vybe.into.includes(tag),
            );
            setVybe(choseNewInterest ? { ...vybe, requested: [], into: vybe.into.filter((tag) => !isSpecificInterest(tag)) } : vybe);
            setSheet(null);
          }}
        />
      )}
    </div>
  );
}
