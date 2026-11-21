import { usePresence } from '../lib/usePresence';
import { Chip, type ChipTone } from './Chip';
import { HintPill } from './HintPill';
import './VybeRow.css';

interface Props {
  label: string;
  hint: string;
  tone: ChipTone;
  tags: string[];
  format: (tag: string) => string;
  onRemove: (tag: string) => void;
  onOpen: () => void;
}

/**
 * One line of the "Your vybe" card. The whole row is a real <button> (stretched underneath),
 * and each chip's X is its own button layered on top, so nothing is nested.
 */
export function VybeRow({ label, hint, tone, tags, format, onRemove, onOpen }: Props) {
  const { entries, exited } = usePresence(tags);

  return (
    <div className="vrow">
      <button type="button" className="vrow-hit" onClick={onOpen}>
        <span className="vrow-label">{label}</span>
      </button>
      <div className="vrow-values">
        {entries.length === 0 ? (
          <HintPill text={hint} />
        ) : (
          entries.map((e) => (
            <Chip
              key={e.key}
              label={format(e.key)}
              tone={tone}
              leaving={e.leaving}
              delay={e.delay}
              onRemove={() => onRemove(e.key)}
              onExited={() => exited(e.key)}
            />
          ))
        )}
      </div>
    </div>
  );
}
