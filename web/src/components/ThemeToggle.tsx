import { useState } from 'react';
import { Moon, Sun } from 'lucide-react';

type Theme = 'light' | 'dark';

function current(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

/** Light is the default; the choice is remembered on this device. */
export function ThemeToggle({ className = 'icon-btn' }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>(current);
  const next: Theme = theme === 'dark' ? 'light' : 'dark';

  const toggle = () => {
    if (next === 'dark') document.documentElement.dataset.theme = 'dark';
    else delete document.documentElement.dataset.theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', next === 'dark' ? '#212126' : '#f6f4f1');
    try {
      localStorage.setItem('vybe.theme', next);
    } catch {
      // private mode: the toggle still works for this visit
    }
    setTheme(next);
  };

  return (
    <button className={className} type="button" aria-label={`Switch to ${next} mode`} onClick={toggle}>
      {theme === 'dark' ? <Sun size={20} strokeWidth={2} /> : <Moon size={20} strokeWidth={2} />}
    </button>
  );
}
