import { useState } from 'react';
import { flushSync } from 'react-dom';
import { Moon, Sun } from 'lucide-react';
import './ThemeToggle.css';

type Theme = 'light' | 'dark';

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

/** Light is the default; the choice is remembered on this device. Switches with a quick cross-fade. */
export function ThemeToggle({ className = 'icon-btn' }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>(current);
  const next: Theme = theme === 'dark' ? 'light' : 'dark';

  const toggle = () => {
    const change = () => {
      flushSync(() => setTheme(next));
      apply(next);
    };
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // The browser's own snapshot cross-fade: cheap, and nothing to compute per frame.
    if (document.startViewTransition && !reduce) document.startViewTransition(change);
    else change();
  };

  return (
    <button className={className} type="button" aria-label={`Switch to ${next} mode`} onClick={toggle}>
      {theme === 'dark' ? <Sun size={20} strokeWidth={2} /> : <Moon size={20} strokeWidth={2} />}
    </button>
  );
}
