// Minimal typings for the parts of culori we use (culori ships no TypeScript types).
declare module 'culori' {
  export interface Oklch {
    mode: 'oklch';
    l: number;
    c: number;
    h?: number;
    alpha?: number;
  }
  export function converter(mode: 'oklch'): (color: string | Oklch) => Oklch | undefined;
  export function clampChroma(color: Oklch, mode?: 'oklch'): Oklch;
  export function formatHex(color: string | Oklch): string | undefined;
}
