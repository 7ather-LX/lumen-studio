import { AlertTriangle, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Logo } from "./Logo";

export function BootScreen({
  error,
  onRetry,
}: {
  error?: string;
  onRetry: () => void;
}) {
  const [busy, setBusy] = useState(false);

  const retry = async () => {
    setBusy(true);
    try {
      if (window.lumen) {
        await window.lumen.restartBackend();
      }
      onRetry();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="boot-screen">
      <div className="boot-aurora" />
      <div className="boot-content">
        <Logo size={58} />
        <div className="boot-wordmark">LUMEN STUDIO</div>
        <p className="boot-tagline">本地优先的 AI 图像工作室</p>
        {error ? (
          <div className="boot-error">
            <AlertTriangle size={18} />
            <div>
              <strong>本地服务没有响应</strong>
              <p>{error}</p>
            </div>
          </div>
        ) : (
          <div className="boot-loader">
            <span className="boot-loader-line" />
            <span>正在启动本地引擎 · 数据不会离开这台电脑</span>
          </div>
        )}
        {error && (
          <button className="button button-ghost boot-retry" onClick={() => void retry()} disabled={busy}>
            <RefreshCw size={15} className={busy ? "spin" : ""} />
            {busy ? "正在重新启动…" : "重试"}
          </button>
        )}
      </div>
      <div className="boot-footer">LOCAL-FIRST · PRIVATE BY DEFAULT · v0.1</div>
    </div>
  );
}
