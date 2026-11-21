import './HintPill.css';

export function HintPill({ text }: { text: string }) {
  return <span className="hint-pill">{text}</span>;
}
