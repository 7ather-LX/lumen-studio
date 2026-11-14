import { Minus, Square, X } from "lucide-react";
import { useStudio } from "../state/StudioContext";

const SECTION_LABELS: Record<string, string> = {
  create: "创作台",
  gallery: "作品库",
  models: "模型引擎",
  learning: "学习中心",
  settings: "偏好设置",
};

export function TitleBar({ page }: { page: string }) {
  const { config } = useStudio();
  const desktop = window.lumen;

  const toggleMaximize = async () => {
    if (!desktop) return;
    await desktop.toggleMaximize();
  };

  return (
    <header className="titlebar" onDoubleClick={toggleMaximize}>
      <div className="titlebar-left">
        <span className="titlebar-wordmark">LUMEN</span>
        <span className="titlebar-divider" />
        <span className="titlebar-section">{SECTION_LABELS[page] ?? ""}</span>
      </div>
      <div className="titlebar-center">
        <span className="titlebar-status">
          <span className="status-dot" />
          本地优先
        </span>
        <span className="titlebar-meta">v{config.version}</span>
      </div>
      {desktop ? (
        <div className="window-controls" onDoubleClick={(event) => event.stopPropagation()}>
          <button className="window-button" onClick={() => void desktop.minimize()} aria-label="最小化">
            <Minus size={13} />
          </button>
          <button className="window-button" onClick={() => void toggleMaximize()} aria-label="最大化">
            <Square size={11} />
          </button>
          <button className="window-button window-close" onClick={() => void desktop.close()} aria-label="关闭">
            <X size={14} />
          </button>
        </div>
      ) : (
        <div className="window-controls window-controls-placeholder" />
      )}
    </header>
  );
}
