import { useRef, useState, type MouseEvent } from 'react';
import { flushSync } from 'react-dom';
import { Moon, Sun } from 'lucide-react';
import './ThemeToggle.css';

type Theme = 'light' | 'dark';

const RIPPLE_MS = 760;
const EASE = 'cubic-bezier(0.65, 0, 0.35, 1)';

function current(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

function apply(theme: Theme) {
  if (theme === 'dark') document.documentElement.dataset.theme = 'dark';
  else delete document.documentElement.dataset.theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#212126' : '#f6f4f1');
  try {
    localStorage.setItem('vybe.theme', theme);
  } catch {
    // private mode: the toggle still works for this visit
  }
}

/**
 * Grain riding the edge of the ripple: a full-screen noise layer masked to a ring that grows with
 * the reveal. It lives in the new page, so it's only visible inside the circle, right at its edge.
 */
function grainRing(x: number, y: number, radius: number) {
  const el = document.createElement('div');
  el.className = 'theme-grain';
  el.style.setProperty('--x', `${x}px`);
  el.style.setProperty('--y', `${y}px`);
  document.body.appendChild(el);
  el.animate([{ '--r': '0px' }, { '--r': `${radius}px` }] as Keyframe[], { duration: RIPPLE_MS, easing: EASE });
  el.animate([{ opacity: 0.5 }, { opacity: 0.4, offset: 0.7 }, { opacity: 0 }], { duration: RIPPLE_MS });
  setTimeout(() => el.remove(), RIPPLE_MS + 50);
}

/**
 * Liquid edge: an SVG turbulence + displacement filter applied to the incoming theme. Its strength
 * starts small and settles to zero, so the reveal wobbles slightly then lands crisp.
 */
const LIQUID_ID = 'vybe-liquid';
const LIQUID_MAX = 10; // px of displacement at the start; subtle on purpose

function liquidFilter(): SVGFEDisplacementMapElement {
  let map = document.querySelector<SVGFEDisplacementMapElement>(`#${LIQUID_ID} feDisplacementMap`);
  if (map) return map;
  const holder = document.createElement('div');
  holder.innerHTML = `<svg width="0" height="0" style="position:absolute" aria-hidden="true">
    <filter id="${LIQUID_ID}" x="-10%" y="-10%" width="120%" height="120%">
      <feTurbulence type="fractalNoise" baseFrequency="0.009 0.012" numOctaves="2" seed="7" result="n"/>
      <feDisplacementMap in="SourceGraphic" in2="n" scale="0" xChannelSelector="R" yChannelSelector="G"/>
    </filter></svg>`;
  document.body.appendChild(holder.firstElementChild!);
  map = document.querySelector<SVGFEDisplacementMapElement>(`#${LIQUID_ID} feDisplacementMap`)!;
  return map;
}

function settleLiquid(map: SVGFEDisplacementMapElement) {
  const start = performance.now();
  const step = (t: number) => {
    const k = Math.min(1, (t - start) / RIPPLE_MS);
    // ease-out: strongest at the start of the reveal, gone by the end
    map.setAttribute('scale', String(LIQUID_MAX * (1 - k) ** 2));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/** Light is the default; the choice is remembered on this device. */
export function ThemeToggle({ className = 'icon-btn' }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>(current);
  const busy = useRef(false); // ignore taps while a switch is still animating
  const next: Theme = theme === 'dark' ? 'light' : 'dark';

  const toggle = (e: MouseEvent<HTMLButtonElement>) => {
    if (busy.current) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!document.startViewTransition || reduce) {
      apply(next);
      setTheme(next);
      return;
    }
    // The new theme spreads out from the button as a circle with a grainy leading edge.
    const b = e.currentTarget.getBoundingClientRect();
    const x = b.left + b.width / 2;
    const y = b.top + b.height / 2;
    const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y)) + 40;

    busy.current = true;
    const liquid = liquidFilter();
    const transition = document.startViewTransition(() => {
      flushSync(() => setTheme(next));
      apply(next);
      grainRing(x, y, radius);
    });
    void transition.ready.then(() => {
      const root = document.documentElement;
      const opts = { duration: RIPPLE_MS, easing: EASE };
      // New theme: grows from the button, arrives slightly blurred and a few px low, settles sharp.
      root.animate(
        {
          clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`],
          filter: [`url(#${LIQUID_ID}) blur(3px)`, `url(#${LIQUID_ID}) blur(0px)`],
          transform: ['translateY(6px) scale(1.006)', 'translateY(0) scale(1)'],
        },
        { ...opts, pseudoElement: '::view-transition-new(root)' },
      );
      // Old theme: softens and drifts up a touch as it's covered.
      root.animate(
        {
          filter: ['blur(0px)', 'blur(5px)'],
          transform: ['translateY(0) scale(1)', 'translateY(-6px) scale(0.994)'],
          opacity: [1, 0.85],
        },
        { ...opts, pseudoElement: '::view-transition-old(root)' },
      );
      settleLiquid(liquid);
    });
    void transition.finished.finally(() => {
      busy.current = false;
    });
  };

  return (
    <button className={className} type="button" aria-label={`Switch to ${next} mode`} onClick={toggle}>
      {theme === 'dark' ? <Sun size={20} strokeWidth={2} /> : <Moon size={20} strokeWidth={2} />}
    </button>
  );
}
