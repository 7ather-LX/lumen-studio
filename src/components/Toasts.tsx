import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { useStudio } from "../state/StudioContext";

export function Toasts() {
  const { toasts, dismissToast } = useStudio();
  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((toast) => (
        <div className={`toast toast-${toast.kind}`} key={toast.id}>
          <span className="toast-icon">
            {toast.kind === "success" && <CheckCircle2 size={17} />}
            {toast.kind === "error" && <AlertTriangle size={17} />}
            {toast.kind === "info" && <Info size={17} />}
          </span>
          <div className="toast-copy">
            <strong>{toast.title}</strong>
            {toast.message && <p>{toast.message}</p>}
          </div>
          <button className="icon-button toast-close" onClick={() => dismissToast(toast.id)} aria-label="关闭">
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
