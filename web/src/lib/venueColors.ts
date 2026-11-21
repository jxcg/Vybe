import { useEffect, useReducer, type CSSProperties } from 'react';
import { clampChroma, converter, formatHex } from 'culori';
import { FastAverageColor } from 'fast-average-color';
import type { Category, Row, VenueColors } from '../contract';

// A touch richer than the original spec values, which read muddy on the dark station chrome.
export const CATEGORY_COLORS: Record<Category, VenueColors> = {
  comedy: { deep: '#45303C', soft: '#6A4C5D', light: '#F0DDE7' },
  games: { deep: '#2F3F2A', soft: '#4F6547', light: '#DFEBD1' },
  food: { deep: '#493424', soft: '#6E513A', light: '#F3DFCA' },
  music: { deep: '#2C3350', soft: '#4B5784', light: '#DCE3F4' },
  culture: { deep: '#3F3A31', soft: '#635B4D', light: '#EEE6D7' },
  bar: { deep: '#46302F', soft: '#6C4B48', light: '#F4DFDB' },
  other: { deep: '#33334A', soft: '#53536E', light: '#E5E2F1' },
};

const toOklch = converter('oklch');

function tone(base: { c: number; h?: number }, l: number, maxChroma: number): string {
  const color = clampChroma({ mode: 'oklch', l, c: Math.min(base.c, maxChroma), h: base.h }, 'oklch');
  return formatHex(color) ?? '#2e2e36';
}

/** A photo's average colour, kept to its hue but clamped into VYBE's muted range. */
export function worldFromColor(hex: string): VenueColors | null {
  const o = toOklch(hex);
  if (!o) return null;
  return { deep: tone(o, 0.3, 0.055), soft: tone(o, 0.42, 0.055), light: tone(o, 0.89, 0.03) };
}

/** Lower a colour's OKLCH lightness by `amount` (used to darken poster tickets near leave time). */
export function darken(hex: string, amount: number): string {
  const o = toOklch(hex);
  if (!o || amount <= 0) return hex;
  return formatHex({ ...o, l: Math.max(0, o.l - amount) }) ?? hex;
}

// Photo extraction is async and cached per URL for the whole session.
const fac = new FastAverageColor();
const pending = new Map<string, Promise<void>>();
const extracted = new Map<string, VenueColors | null>();

function extract(url: string): Promise<void> {
  let p = pending.get(url);
  if (!p) {
    p = fac
      .getColorAsync(url, { crossOrigin: 'anonymous', algorithm: 'dominant' })
      .then((result) => worldFromColor(result.hex))
      .catch(() => null) // CORS or a broken image: fall back to the category colours
      .then((colors) => {
        extracted.set(url, colors);
      });
    pending.set(url, p);
  }
  return p;
}

/** Server colours → colours extracted from the photo → category fallback. */
export function useVenueColors(row: Row, displayedPhoto?: string | null): VenueColors {
  const url = displayedPhoto === undefined ? (row.colors ? null : row.photo_url) : displayedPhoto;
  const [, refresh] = useReducer((n: number) => n + 1, 0);

  useEffect(() => {
    if (!url || extracted.has(url)) return;
    let alive = true;
    void extract(url).then(() => alive && refresh());
    return () => {
      alive = false;
    };
  }, [url]);

  return (url ? extracted.get(url) : null) ?? row.colors ?? CATEGORY_COLORS[row.category];
}

/** CSS custom properties that put a subtree into the venue's colour world. */
export function venueStyle(c: VenueColors): CSSProperties {
  return { '--deep': c.deep, '--soft': c.soft, '--light': c.light } as CSSProperties;
}
