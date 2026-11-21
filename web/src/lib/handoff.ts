import type { Shape } from './morph';

// Shapes passed between screens so one element can appear to travel across a screen change
// (the mic becomes the loading orb, the orb becomes the board's count). Taken once, then gone.
const shapes = new Map<string, Shape>();

export const handoff = {
  put(key: 'orb', shape: Shape): void {
    shapes.set(key, shape);
  },
  take(key: 'orb'): Shape | undefined {
    const shape = shapes.get(key);
    shapes.delete(key);
    return shape;
  },
};
