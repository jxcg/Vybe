import './SentenceSlot.css';

const EXAMPLE = 'Me and two mates, want a laugh, nothing over a tenner.';

export function SentenceSlot({ text }: { text: string }) {
  if (!text) return <p className="slot slot--empty">{EXAMPLE}</p>;
  return (
    <div className="slot" aria-live="polite">
      <p className="slot-label">You said</p>
      <p className="slot-text">{`“${text}”`}</p>
    </div>
  );
}
