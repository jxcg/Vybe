import { useState, type MouseEvent } from 'react';
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

/** Light is the default; the choice is remembered on this device. */
export function ThemeToggle({ className = 'icon-btn' }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>(current);
  const next: Theme = theme === 'dark' ? 'light' : 'dark';

  const toggle = (e: MouseEvent<HTMLButtonElement>) => {
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

    const transition = document.startViewTransition(() => {
      flushSync(() => setTheme(next));
      apply(next);
      grainRing(x, y, radius);
    });
    void transition.ready.then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        { duration: RIPPLE_MS, easing: EASE, pseudoElement: '::view-transition-new(root)' },
      );
    });
  };

  return (
    <button className={className} type="button" aria-label={`Switch to ${next} mode`} onClick={toggle}>
      {theme === 'dark' ? <Sun size={20} strokeWidth={2} /> : <Moon size={20} strokeWidth={2} />}
    </button>
  );
}
