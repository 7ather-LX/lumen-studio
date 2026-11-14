import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api";
import type { Presets, Provider, RuntimeConfig, RuntimeInfo, Settings, Stats } from "../types";
import { errorMessage } from "../lib/utils";

export type ToastKind = "success" | "error" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  message?: string;
}

interface StudioContextValue {
  config: RuntimeConfig;
  runtime: RuntimeInfo | null;
  settings: Settings | null;
  providers: Provider[];
  presets: Presets | null;
  stats: Stats | null;
  ready: boolean;
  galleryVersion: number;
  refreshAll: () => Promise<void>;
  refreshRuntime: () => Promise<void>;
  refreshSettings: () => Promise<void>;
  refreshProviders: () => Promise<void>;
  refreshStats: () => Promise<void>;
  notify: (title: string, message?: string) => void;
  toast: (message: string) => void;
  fail: (error: unknown, title?: string) => void;
  bumpGallery: () => void;
  toasts: Toast[];
  dismissToast: (id: number) => void;
}

const StudioContext = createContext<StudioContextValue | null>(null);

let toastId = 1;

export function StudioProvider({ config, children }: { config: RuntimeConfig; children: ReactNode }) {
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [presets, setPresets] = useState<Presets | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [ready, setReady] = useState(false);
  const [galleryVersion, setGalleryVersion] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const readyRef = useRef(false);

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  const pushToast = useCallback(
    (kind: ToastKind, title: string, message?: string) => {
      const id = toastId++;
      setToasts((current) => [...current.slice(-3), { id, kind, title, message }]);
      window.setTimeout(() => dismissToast(id), kind === "error" ? 8000 : 4200);
    },
    [dismissToast],
  );

  const notify = useCallback(
    (title: string, message?: string) => pushToast("success", title, message),
    [pushToast],
  );
  const toast = useCallback((message: string) => notify(message), [notify]);
  const fail = useCallback(
    (error: unknown, title = "操作失败") => pushToast("error", title, errorMessage(error)),
    [pushToast],
  );

  const refreshRuntime = useCallback(async () => {
    try {
      const value = await api.runtime();
      setRuntime(value);
    } catch (error) {
      if (readyRef.current) fail(error, "无法读取硬件状态");
    }
  }, [fail]);

  const refreshSettings = useCallback(async () => {
    try {
      setSettings(await api.settings());
    } catch (error) {
      fail(error, "无法读取设置");
    }
  }, [fail]);

  const refreshProviders = useCallback(async () => {
    try {
      setProviders(await api.providers());
    } catch (error) {
      fail(error, "无法读取模型供应商");
    }
  }, [fail]);

  const refreshStats = useCallback(async () => {
    try {
      setStats(await api.stats());
    } catch {
      /* stats are non-critical */
    }
  }, []);

  const refreshAll = useCallback(async () => {
    const results = await Promise.allSettled([
      api.runtime(),
      api.settings(),
      api.providers(),
      api.presets(),
      api.stats(),
    ]);
    const [runtimeResult, settingsResult, providersResult, presetsResult, statsResult] = results;
    if (runtimeResult.status === "fulfilled") setRuntime(runtimeResult.value);
    if (settingsResult.status === "fulfilled") setSettings(settingsResult.value);
    if (providersResult.status === "fulfilled") setProviders(providersResult.value);
    if (presetsResult.status === "fulfilled") setPresets(presetsResult.value);
    if (statsResult.status === "fulfilled") setStats(statsResult.value);
    const rejected = results.find((item) => item.status === "rejected");
    if (rejected?.status === "rejected") {
      fail(rejected.reason, "初始化失败");
    }
    setReady(true);
    readyRef.current = true;
  }, [fail]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshRuntime();
    }, 25_000);
    return () => window.clearInterval(timer);
  }, [refreshRuntime]);

  const bumpGallery = useCallback(() => {
    setGalleryVersion((value) => value + 1);
    void refreshStats();
  }, [refreshStats]);

  const dataReady = ready && Boolean(runtime) && Boolean(settings) && providers.length > 0 && Boolean(presets);

  const value = useMemo<StudioContextValue>(
    () => ({
      config,
      runtime,
      settings,
      providers,
      presets,
      stats,
      ready: dataReady,
      galleryVersion,
      refreshAll,
      refreshRuntime,
      refreshSettings,
      refreshProviders,
      refreshStats,
      notify,
      toast,
      fail,
      bumpGallery,
      toasts,
      dismissToast,
    }),
    [
      config,
      runtime,
      settings,
      providers,
      presets,
      stats,
      dataReady,
      galleryVersion,
      refreshAll,
      refreshRuntime,
      refreshSettings,
      refreshProviders,
      refreshStats,
      notify,
      toast,
      fail,
      bumpGallery,
      toasts,
      dismissToast,
    ],
  );

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
}

export function useStudio(): StudioContextValue {
  const context = useContext(StudioContext);
  if (!context) throw new Error("useStudio must be used within StudioProvider");
  return context;
}
