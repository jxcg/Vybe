import type { Budget, ChipsMsg, Prefs } from '../contract';

/** What the user has told us about tonight. Tags are stored lowercase. */
export interface Vybe {
  into: string[];
  notInto: string[];
  budget: Budget | null;
  student: boolean;
  adult: boolean;
  /** people including you; null = not said yet */
  company: number | null;
  /** age range, e.g. "18-21"; null = not said. Used as a gentle ranking factor, never shown to others. */
  age?: string | null;
  /** "chill" or "lively"; null = no preference */
  vibe?: string | null;
}

export const EMPTY_VYBE: Vybe = {
  into: [],
  notInto: [],
  budget: null,
  student: false,
  adult: true,
  company: null,
  age: null,
  vibe: null,
};

export const AGE_OPTIONS: { value: string; label: string }[] = [
  { value: 'under18', label: 'Under 18' },
  { value: '18-21', label: '18–21' },
  { value: '22-25', label: '22–25' },
  { value: '26-35', label: '26–35' },
  { value: '36+', label: '36+' },
];

export const VIBE_OPTIONS: { value: string; label: string }[] = [
  { value: 'chill', label: 'Laid-back' },
  { value: 'lively', label: 'Lively' },
];

export function ageLabel(age: string): string {
  return AGE_OPTIONS.find((o) => o.value === age)?.label ?? age;
}

export function vibeLabel(vibe: string): string {
  return VIBE_OPTIONS.find((o) => o.value === vibe)?.label ?? vibe;
}

export const INTO_SUGGESTIONS = [
  'a laugh',
  'chill',
  'active',
  'competitive',
  'food',
  'live music',
  'culture',
  'late night',
];

export const NOT_INTO_SUGGESTIONS = ['clubs', 'loud music', 'outdoors', 'late nights', 'queues'];

export const BUDGET_OPTIONS: { value: Budget; label: string }[] = [
  { value: 10, label: 'Under £10' },
  { value: 20, label: 'Under £20' },
  { value: 999, label: 'Any' },
];

export const COMPANY_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: 'Just me' },
  { value: 2, label: '+1' },
  { value: 3, label: '+2' },
  { value: 4, label: '+3' },
  { value: 5, label: '+4' },
];

export function tagLabel(tag: string): string {
  return tag.charAt(0).toUpperCase() + tag.slice(1);
}

export function budgetLabel(budget: Budget): string {
  return budget === 999 ? 'Any budget' : `Under £${budget}`;
}

export function companyLabel(company: number): string {
  if (company <= 1) return 'Just you';
  const mates = company - 1;
  return `You + ${mates} ${mates === 1 ? 'mate' : 'mates'}`;
}

export function toPrefs(v: Vybe): Prefs {
  return {
    budget: v.budget ?? 999,
    student: v.student,
    adult: v.adult,
    include: v.into,
    exclude: v.notInto,
    company: v.company ?? 1,
    age: v.age ?? null,
    vibe: v.vibe ?? null,
  };
}

const norm = (tags: string[]) => tags.map((t) => t.trim().toLowerCase()).filter(Boolean);

/** Fold a server `chips` message into the current vybe. A tag can't be both into and not-into. */
export function mergeChips(v: Vybe, chips: ChipsMsg): Vybe {
  const include = norm(chips.include);
  const exclude = norm(chips.exclude);
  const into = [...v.into.filter((t) => !exclude.includes(t)), ...include];
  const notInto = [...v.notInto.filter((t) => !include.includes(t)), ...exclude];
  return {
    ...v,
    into: [...new Set(into)],
    notInto: [...new Set(notInto)],
    budget: chips.budget ?? v.budget,
    student: chips.student ?? v.student,
    company: chips.company ?? v.company,
  };
}

export function fromPrefs(prefs: Prefs): Vybe {
  return {
    into: prefs.include, notInto: prefs.exclude, budget: prefs.budget,
    student: prefs.student, adult: prefs.adult, company: prefs.company,
    age: prefs.age, vibe: prefs.vibe,
  };
}

export function updatePersonal(personal: Vybe, before: Vybe, after: Vybe): Vybe {
  const updated = { ...personal };
  function copyChange<K extends keyof Vybe>(key: K) {
    if (before[key] !== after[key]) updated[key] = after[key];
  }
  (Object.keys(after) as (keyof Vybe)[]).forEach(copyChange);
  return updated;
}
