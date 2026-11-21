// Small FLIP / shared-element helpers built on the Web Animations API.
// Ghost elements are fixed-position stand-ins that fly between two measured shapes and then remove
// themselves, so the real React tree can switch layout instantly underneath.

export const MORPH_MS = 340;
export const MORPH_EASE = 'cubic-bezier(0.32, 0.72, 0, 1)';

export interface Shape {
  left: number;
  top: number;
  width: number;
  height: number;
  bg: string;
  border: string;
  color: string;
  /** width of the first svg inside, if any */
  icon: number;
}

export function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function shapeOf(el: Element): Shape {
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  const svg = el.querySelector('svg');
  return {
    left: r.left,
    top: r.top,
    width: r.width,
    height: r.height,
    bg: cs.backgroundColor,
    border: cs.borderTopWidth === '0px' ? 'transparent' : cs.borderTopColor,
    color: cs.color,
    icon: svg ? svg.getBoundingClientRect().width : 0,
  };
}

const frame = (s: Shape): Keyframe => ({
  left: `${s.left}px`,
  top: `${s.top}px`,
  width: `${s.width}px`,
  height: `${s.height}px`,
  backgroundColor: s.bg,
  borderColor: s.border,
  color: s.color,
});

/** Resolves when the animation ends, or after a grace period if the page stops rendering frames. */
export const whenDone = (a: Animation): Promise<void> => {
  const timing = a.effect?.getTiming();
  const total = Number(timing?.duration ?? 0) + Number(timing?.delay ?? 0);
  return Promise.race([
    a.finished.then(
      () => undefined,
      () => undefined,
    ),
    new Promise<void>((resolve) => window.setTimeout(resolve, total + 250)),
  ]);
};

interface GhostOptions {
  /** svg to carry inside the ghost, resized from `from.icon` to `to.icon` */
  icon?: SVGElement | null;
  /** opacity keyframes, e.g. [0, 1] to materialise or [1, 0] to dissolve */
  opacity?: [number, number];
}

/** A fixed stand-in that animates from one shape to another, then removes itself. */
export function ghost(from: Shape, to: Shape, { icon, opacity }: GhostOptions = {}): Promise<void> {
  const el = document.createElement('div');
  el.className = 'morph-ghost';
  el.setAttribute('aria-hidden', 'true');
  const timing: KeyframeAnimationOptions = { duration: MORPH_MS, easing: MORPH_EASE, fill: 'both' };

  const animations: Animation[] = [];
  if (icon) {
    const svg = icon.cloneNode(true) as SVGElement;
    el.appendChild(svg);
    animations.push(
      svg.animate(
        [
          { width: `${from.icon}px`, height: `${from.icon}px` },
          { width: `${to.icon}px`, height: `${to.icon}px` },
        ],
        timing,
      ),
    );
  }
  document.body.appendChild(el);
  animations.push(el.animate([frame(from), frame(to)], timing));
  if (opacity) {
    // Linear time (not the shape's ease-out), so a dissolving bar stays visible while it
    // retracts and a materialising one firms up early.
    const [a, b] = opacity;
    const frames: Keyframe[] =
      a < b
        ? [
            { opacity: a, offset: 0 },
            { opacity: b, offset: 0.25 },
            { opacity: b, offset: 1 },
          ]
        : [
            { opacity: a, offset: 0 },
            { opacity: a, offset: 0.4 },
            { opacity: b, offset: 0.7 },
            { opacity: b, offset: 1 },
          ];
    animations.push(el.animate(frames, { ...timing, easing: 'linear' }));
  }
  return Promise.all(animations.map(whenDone)).then(() => el.remove());
}

/**
 * Freezes a snapshot of `el` where it is now and fades it out, so content can leave gracefully
 * even though React has already unmounted it.
 */
export function fadeOutCopy(el: HTMLElement, prepare?: (copy: HTMLElement) => void): void {
  const r = el.getBoundingClientRect();
  const copy = el.cloneNode(true) as HTMLElement;
  copy.setAttribute('aria-hidden', 'true');
  copy.inert = true;
  prepare?.(copy);
  Object.assign(copy.style, {
    position: 'fixed',
    left: `${r.left}px`,
    top: `${r.top}px`,
    width: `${r.width}px`,
    height: `${r.height}px`,
    margin: '0',
    pointerEvents: 'none',
    // Behind the page: the card slides over the dissolving text instead of under it.
    zIndex: '-1',
  });
  document.body.appendChild(copy);
  const a = copy.animate([{ opacity: 1 }, { opacity: 0 }], {
    duration: MORPH_MS * 0.4,
    easing: 'ease-out',
    fill: 'forwards',
  });
  void whenDone(a).then(() => copy.remove());
}

/** FLIP: the element has already moved; animate it from where it used to be. */
export function slideFrom(el: Element, previousTop: number): void {
  const dy = previousTop - el.getBoundingClientRect().top;
  if (Math.abs(dy) < 1) return;
  el.animate([{ transform: `translateY(${dy}px)` }, { transform: 'none' }], {
    duration: MORPH_MS,
    easing: MORPH_EASE,
  });
}

export function fadeIn(els: Iterable<Element>, delay = 0, duration = MORPH_MS * 0.5): void {
  for (const el of els) {
    el.animate([{ opacity: 0 }, { opacity: 1 }], { duration, delay, easing: 'ease-out', fill: 'backwards' });
  }
}
