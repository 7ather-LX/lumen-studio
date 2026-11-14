import { Brain, Cpu, Images, Settings, Sparkles } from "lucide-react";
import { formatVram } from "../lib/utils";
import { useStudio } from "../state/StudioContext";
import type { PageId } from "../types";
import { Logo } from "./Logo";

const NAV: Array<{ id: PageId; label: string; icon: typeof Sparkles }> = [
  { id: "create", label: "创作", icon: Sparkles },
  { id: "gallery", label: "作品", icon: Images },
  { id: "models", label: "模型", icon: Cpu },
  { id: "learning", label: "学习", icon: Brain },
  { id: "settings", label: "设置", icon: Settings },
];

export function Sidebar({ page, onNavigate }: { page: PageId; onNavigate: (page: PageId) => void }) {
  const { runtime, providers, stats } = useStudio();
  const available = providers.filter((provider) => provider.enabled && provider.availability.available).length;
  const free = runtime?.low_vram?.free_vram_mb ?? null;
  const low = free !== null && free < 4000;

  return (
    <aside className="sidebar">
      <button className="sidebar-brand" onClick={() => onNavigate("create")} aria-label="Lumen Studio 首页">
        <Logo size={30} />
      </button>

      <nav className="sidebar-nav">
        {NAV.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={`nav-item ${page === item.id ? "active" : ""}`}
              onClick={() => onNavigate(item.id)}
              title={item.label}
            >
              <span className="nav-icon">
                <Icon size={19} strokeWidth={1.7} />
              </span>
              <span>{item.label}</span>
              {item.id === "gallery" && stats?.images ? <span className="nav-count">{stats.images}</span> : null}
            </button>
          );
        })}
      </nav>

      <div className="sidebar-bottom">
        <button className="gpu-chip" onClick={() => onNavigate("models")} title="查看硬件与本地引擎">
          <span className={`gpu-dot ${low ? "warn" : ""}`} />
          <span className="gpu-copy">
            <strong>{free !== null ? formatVram(free) : "CPU"}</strong>
            <small>{low ? "显存较低" : "可用显存"}</small>
          </span>
        </button>
        <div className="sidebar-foot">
          <span>{available} 个引擎</span>
          <span className="sidebar-foot-dot" />
          <span>本地数据</span>
        </div>
      </div>
    </aside>
  );
}
