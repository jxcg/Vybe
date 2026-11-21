import './FuseLine.css';

interface Props {
  /** 0–1: share of the last hour still left before leave_by. */
  fraction: number;
}

export function FuseLine({ fraction }: Props) {
  const clamped = Math.min(1, Math.max(0, fraction));
  return (
    <div className="fuse" aria-hidden="true">
      <div className="fuse-fill" style={{ transform: `scaleX(${clamped})` }} />
    </div>
  );
}
