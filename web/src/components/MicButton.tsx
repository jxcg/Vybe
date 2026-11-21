import type { Ref } from 'react';
import { Mic } from 'lucide-react';
import './MicButton.css';

export type TalkPhase = 'idle' | 'listening' | 'thinking';

interface Props {
  phase: TalkPhase;
  onPress: () => void;
  buttonRef?: Ref<HTMLButtonElement>;
}

export function MicButton({ phase, onPress, buttonRef }: Props) {
  return (
    <div className={`mic mic--${phase}`}>
      <span className="mic-ring" aria-hidden="true" />
      <button
        ref={buttonRef}
        type="button"
        className="mic-btn"
        onClick={onPress}
        disabled={phase === 'thinking'}
        aria-label={phase === 'listening' ? 'Stop and send' : 'Tap to talk'}
      >
        <Mic size={30} strokeWidth={2} aria-hidden="true" />
      </button>
    </div>
  );
}
