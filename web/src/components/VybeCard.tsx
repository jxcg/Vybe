import { ageLabel, budgetLabel, companyLabel, tagLabel, vibeLabel, type Vybe } from '../lib/vybe';
import type { Budget } from '../contract';
import { VybeRow } from './VybeRow';
import './VybeCard.css';

export type RowKey = 'into' | 'notInto' | 'budget' | 'company' | 'age' | 'vibe';

interface Props {
  vybe: Vybe;
  onChange: (vybe: Vybe) => void;
  onOpen: (row: RowKey) => void;
}

export function VybeCard({ vybe, onChange, onOpen }: Props) {
  return (
    <section className="vcard" aria-label="Your vybe">
      <h2 className="vcard-label">Your vybe</h2>
      <VybeRow
        label="Into"
        hint="e.g. a laugh, chill, active"
        tone="into"
        tags={vybe.into}
        format={tagLabel}
        onRemove={(tag) => onChange({ ...vybe, into: vybe.into.filter((t) => t !== tag) })}
        onOpen={() => onOpen('into')}
      />
      <VybeRow
        label="Not into"
        hint="e.g. clubs, loud music"
        tone="notinto"
        tags={vybe.notInto}
        format={tagLabel}
        onRemove={(tag) => onChange({ ...vybe, notInto: vybe.notInto.filter((t) => t !== tag) })}
        onOpen={() => onOpen('notInto')}
      />
      <VybeRow
        label="Budget"
        hint="e.g. under a tenner"
        tone="neutral"
        tags={vybe.budget === null ? [] : [String(vybe.budget)]}
        format={(tag) => budgetLabel(Number(tag) as Budget)}
        onRemove={() => onChange({ ...vybe, budget: null })}
        onOpen={() => onOpen('budget')}
      />
      <VybeRow
        label="Who's coming"
        hint="e.g. just you, or mates?"
        tone="neutral"
        tags={vybe.company === null ? [] : [String(vybe.company)]}
        format={(tag) => companyLabel(Number(tag))}
        onRemove={() => onChange({ ...vybe, company: null })}
        onOpen={() => onOpen('company')}
      />
      <VybeRow
        label="Age"
        hint="helps us pick places"
        tone="neutral"
        tags={vybe.age ? [vybe.age] : []}
        format={ageLabel}
        onRemove={() => onChange({ ...vybe, age: null, adult: true })}
        onOpen={() => onOpen('age')}
      />
      <VybeRow
        label="Vibe"
        hint="laid-back or lively?"
        tone="neutral"
        tags={vybe.vibe ? [vybe.vibe] : []}
        format={vibeLabel}
        onRemove={() => onChange({ ...vybe, vibe: null })}
        onOpen={() => onOpen('vibe')}
      />
    </section>
  );
}
