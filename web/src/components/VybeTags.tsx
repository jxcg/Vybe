import { ageLabel, budgetLabel, companyLabel, tagLabel, vibeLabel, type Vybe } from '../lib/vybe';
import { Chip, type ChipTone } from './Chip';
import './VybeTags.css';

interface Tag {
  key: string;
  label: string;
  tone: ChipTone;
  remove: (v: Vybe) => Vybe;
}

/** What we picked up from what you said, as removable chips (the phone onboarding's compact vybe). */
export function VybeTags({ vybe, onChange }: { vybe: Vybe; onChange: (v: Vybe) => void }) {
  const tags: Tag[] = [
    ...vybe.into.map((t) => ({
      key: `in-${t}`,
      label: tagLabel(t),
      tone: 'into' as const,
      remove: (v: Vybe) => ({ ...v, into: v.into.filter((x) => x !== t) }),
    })),
    ...vybe.notInto.map((t) => ({
      key: `out-${t}`,
      label: tagLabel(t),
      tone: 'notinto' as const,
      remove: (v: Vybe) => ({ ...v, notInto: v.notInto.filter((x) => x !== t) }),
    })),
    ...(vybe.budget !== null && vybe.budget !== 999
      ? [{ key: 'budget', label: budgetLabel(vybe.budget), tone: 'neutral' as const, remove: (v: Vybe) => ({ ...v, budget: null }) }]
      : []),
    ...(vybe.company !== null
      ? [{ key: 'company', label: companyLabel(vybe.company), tone: 'neutral' as const, remove: (v: Vybe) => ({ ...v, company: null }) }]
      : []),
    ...(vybe.student
      ? [{ key: 'student', label: 'Student', tone: 'neutral' as const, remove: (v: Vybe) => ({ ...v, student: false }) }]
      : []),
    ...(vybe.age
      ? [{ key: 'age', label: ageLabel(vybe.age), tone: 'neutral' as const, remove: (v: Vybe) => ({ ...v, age: null, adult: true }) }]
      : []),
    ...(vybe.vibe
      ? [{ key: 'vibe', label: vibeLabel(vybe.vibe), tone: 'neutral' as const, remove: (v: Vybe) => ({ ...v, vibe: null }) }]
      : []),
  ];
  if (!tags.length) return null;
  return (
    <div className="start-tags" aria-label="What we picked up">
      {tags.map((t, i) => (
        <Chip
          key={t.key}
          label={t.label}
          tone={t.tone}
          leaving={false}
          delay={i * 40}
          onRemove={() => onChange(t.remove(vybe))}
          onExited={() => {}}
        />
      ))}
    </div>
  );
}
