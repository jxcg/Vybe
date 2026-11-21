import { useEffect } from 'react';
import { useStore, type Toast } from '../state/store';
import './Toasts.css';

const TOAST_MS = 3000;

function ToastItem({ toast }: { toast: Toast }) {
  const { dispatch } = useStore();
  useEffect(() => {
    const t = window.setTimeout(() => dispatch({ type: 'dismiss_toast', id: toast.id }), TOAST_MS);
    return () => window.clearTimeout(t);
  }, [toast.id, dispatch]);
  return <div className="toast t-secondary">{toast.text}</div>;
}

export function Toasts() {
  const { state } = useStore();
  const toast = state.toasts[0];
  if (!toast) return null;
  return (
    <div className="toasts" role="status" aria-live="polite">
      <ToastItem key={toast.id} toast={toast} />
    </div>
  );
}
