import { useEffect, useState } from "react";
import { api } from "./api";
import { BootScreen } from "./components/BootScreen";
import { Sidebar } from "./components/Sidebar";
import { TitleBar } from "./components/TitleBar";
import { Toasts } from "./components/Toasts";
import { CreatePage } from "./pages/CreatePage";
import { GalleryPage } from "./pages/GalleryPage";
import { LearningPage } from "./pages/LearningPage";
import { ModelsPage } from "./pages/ModelsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StudioProvider, useStudio } from "./state/StudioContext";
import type { PageId, RuntimeConfig } from "./types";

function fallbackRuntime(): RuntimeConfig {
  return {
    api: "http://127.0.0.1:8765",
    token: "",
    version: "0.1.0",
    dataDir: "",
    resourcesDir: "",
    isPackaged: false,
    platform: "web",
  };
}

export default function App() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [error, setError] = useState<string>("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      try {
        const runtime = window.lumen ? await window.lumen.getRuntime() : fallbackRuntime();
        if (!runtime.api) throw new Error("本地服务尚未就绪");
        api.configure(runtime);
        await api.health();
        if (!cancelled) {
          setConfig(runtime);
          setError("");
        }
      } catch (bootError) {
        if (!cancelled) {
          setError(bootError instanceof Error ? bootError.message : String(bootError));
        }
      }
    }
    void boot();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (!config) {
    return <BootScreen error={error} onRetry={() => setAttempt((value) => value + 1)} />;
  }

  return (
    <StudioProvider config={config}>
      <StudioShell />
    </StudioProvider>
  );
}

function StudioShell() {
  const { ready, refreshAll } = useStudio();
  const [page, setPage] = useState<PageId>("create");

  useEffect(() => {
    if (ready) return;
    const timer = window.setInterval(() => {
      void refreshAll();
    }, 2200);
    return () => window.clearInterval(timer);
  }, [ready, refreshAll]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      const map: Record<string, PageId> = {
        "1": "create",
        "2": "gallery",
        "3": "models",
        "4": "learning",
        "5": "settings",
      };
      const target = map[event.key];
      if (target) {
        event.preventDefault();
        setPage(target);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  if (!ready) {
    return <BootScreen onRetry={() => void refreshAll()} />;
  }

  return (
    <div className="app">
      <TitleBar page={page} />
      <div className="app-body">
        <Sidebar page={page} onNavigate={setPage} />
        <main className="workspace">
          <div className="page-layer" hidden={page !== "create"}>
            <CreatePage active={page === "create"} onNavigate={setPage} />
          </div>
          {page === "gallery" && <GalleryPage onNavigate={setPage} />}
          {page === "models" && <ModelsPage onNavigate={setPage} />}
          {page === "learning" && <LearningPage onNavigate={setPage} />}
          {page === "settings" && <SettingsPage />}
        </main>
      </div>
      <Toasts />
    </div>
  );
}
