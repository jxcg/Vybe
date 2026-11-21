import { useEffect, useState } from 'react';

const KEYBOARD_MIN_PX = 150;

/** True while the on-screen keyboard covers part of the page (iOS Safari + Android Chrome). */
export function useKeyboardOpen(): boolean {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const check = () => setOpen(window.innerHeight - vv.height * vv.scale > KEYBOARD_MIN_PX);
    vv.addEventListener('resize', check);
    check();
    return () => vv.removeEventListener('resize', check);
  }, []);

  return open;
}
