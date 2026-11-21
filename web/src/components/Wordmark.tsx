import './Wordmark.css';

interface Props {
  size?: 'sm' | 'lg';
}

export function Wordmark({ size = 'sm' }: Props) {
  return (
    <span className={`wordmark wordmark--${size}`} aria-label="VYBE">
      VYBE
    </span>
  );
}
