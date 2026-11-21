import './RainMark.css';

/** Three slanted streaks drifting down: a quiet, bespoke stand-in for a rain icon. */
export function RainMark() {
  return (
    <span className="rain" aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  );
}
