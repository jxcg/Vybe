import type { Status } from '../contract';
import { STATUS_LABEL } from '../lib/format';
import './StatusText.css';

interface Props {
  status: Status;
  className?: string;
}

/** Renders the server's status. Colour only, never a pill. */
export function StatusText({ status, className = '' }: Props) {
  return (
    <span className={`status status--${status} ${className}`}>
      {STATUS_LABEL[status]}
    </span>
  );
}
