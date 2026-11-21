import { useEffect, useId, useState } from 'react';
import { Check } from 'lucide-react';
import {
  BUDGET_OPTIONS,
  COMPANY_OPTIONS,
  INTO_SUGGESTIONS,
  NOT_INTO_SUGGESTIONS,
  tagLabel,
  type Vybe,
} from '../lib/vybe';
import type { ChipTone } from './Chip';
import type { RowKey } from './VybeCard';
import './RowSheet.css';

const TITLES: Record<RowKey, string> = {
  into: 'Into',
  notInto: 'Not into',
  budget: 'Budget',
  company: "Who's coming",
};

interface Props {
  row: RowKey;
  vybe: Vybe;
  onDone: (vybe: Vybe) => void;
  onCancel: () => void;
}

interface OptionProps {
  label: string;
  on: boolean;
  tone: ChipTone;
  check?: boolean;
  onToggle: () => void;
}

function Option({ label, on, tone, check, onToggle }: OptionProps) {
  return (
    <button
      type="button"
      className={`sheet-opt${on ? ` sheet-opt--on sheet-opt--${tone}` : ''}`}
      aria-pressed={on}
      onClick={onToggle}
    >
      {check && on && <Check size={16} strokeWidth={2} aria-hidden="true" />}
      {label}
    </button>
  );
}

const toggle = (list: string[], tag: string) =>
  list.includes(tag) ? list.filter((t) => t !== tag) : [...list, tag];

export function RowSheet({ row, vybe, onDone, onCancel }: Props) {
  const [draft, setDraft] = useState(vybe);
  const [closing, setClosing] = useState<'done' | 'cancel' | null>(null);
  const titleId = useId();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setClosing('cancel');
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const tagOptions = (key: 'into' | 'notInto', suggestions: string[], tone: ChipTone) =>
    [...new Set([...suggestions, ...draft[key]])].map((tag) => (
      <Option
        key={tag}
        label={tagLabel(tag)}
        tone={tone}
        on={draft[key].includes(tag)}
        onToggle={() => setDraft({ ...draft, [key]: toggle(draft[key], tag) })}
      />
    ));

  return (
    <div className={`sheet-layer${closing ? ' is-closing' : ''}`}>
      <div className="sheet-scrim" onClick={() => setClosing('cancel')} />
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onAnimationEnd={(e) => {
          if (!closing || e.target !== e.currentTarget) return;
          if (closing === 'done') onDone(draft);
          else onCancel();
        }}
      >
        <div className="sheet-handle" aria-hidden="true" />
        <h2 id={titleId} className="t-section sheet-title">
          {TITLES[row]}
        </h2>

        <div className="sheet-opts">
          {row === 'into' && tagOptions('into', INTO_SUGGESTIONS, 'into')}
          {row === 'notInto' && tagOptions('notInto', NOT_INTO_SUGGESTIONS, 'notinto')}
          {row === 'budget' &&
            BUDGET_OPTIONS.map((o) => (
              <Option
                key={o.value}
                label={o.label}
                tone="neutral"
                on={draft.budget === o.value}
                onToggle={() => setDraft({ ...draft, budget: o.value })}
              />
            ))}
          {row === 'company' &&
            COMPANY_OPTIONS.map((o) => (
              <Option
                key={o.value}
                label={o.label}
                tone="neutral"
                on={draft.company === o.value}
                onToggle={() => setDraft({ ...draft, company: o.value })}
              />
            ))}
        </div>

        {row === 'budget' && (
          <div className="sheet-opts sheet-opts--toggles">
            <Option
              label="Student"
              tone="neutral"
              check
              on={draft.student}
              onToggle={() => setDraft({ ...draft, student: !draft.student })}
            />
            <Option
              label="Over 18"
              tone="neutral"
              check
              on={draft.adult}
              onToggle={() => setDraft({ ...draft, adult: !draft.adult })}
            />
          </div>
        )}

        <button type="button" className="pill pill--primary sheet-done" onClick={() => setClosing('done')}>
          Done
        </button>
      </div>
    </div>
  );
}
