import { useEffect, useRef, useState, type Ref } from 'react';
import { Keyboard, Mic } from 'lucide-react';
import './TypeField.css';

const DEBOUNCE_MS = 900;

interface Props {
  inputRef: Ref<HTMLInputElement>;
  formRef: Ref<HTMLFormElement>;
  /** viaEnter: the user pressed Enter (not the debounce) — a signal to open the board. */
  onSend: (text: string, viaEnter: boolean) => void;
  onVoice: () => void;
}

export function TypeField({ inputRef, formRef, onSend, onVoice }: Props) {
  const [value, setValue] = useState('');
  const timer = useRef<number | undefined>(undefined);
  const lastSent = useRef('');

  const flush = (text: string, viaEnter = false) => {
    window.clearTimeout(timer.current);
    const trimmed = text.trim();
    if (!trimmed || trimmed === lastSent.current) return;
    lastSent.current = trimmed;
    onSend(trimmed, viaEnter);
  };

  useEffect(() => () => window.clearTimeout(timer.current), []);

  return (
    <form
      ref={formRef}
      className="typefield"
      onSubmit={(e) => {
        e.preventDefault();
        flush(value, true);
      }}
    >
      <Keyboard className="typefield-icon" size={18} strokeWidth={2} aria-hidden="true" />
      <input
        ref={inputRef}
        className="typefield-input"
        type="text"
        enterKeyHint="send"
        autoComplete="off"
        placeholder="e.g. chill food, under £15"
        aria-label="What are you in the mood for?"
        value={value}
        onChange={(e) => {
          const next = e.target.value;
          setValue(next);
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => flush(next), DEBOUNCE_MS);
        }}
      />
      <button type="button" className="typefield-mic" onClick={onVoice} aria-label="Talk instead">
        <Mic size={18} strokeWidth={2} aria-hidden="true" />
      </button>
    </form>
  );
}
