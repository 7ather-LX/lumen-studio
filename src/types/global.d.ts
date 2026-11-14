import type { RuntimeConfig, UpdateEvent } from "../types";

export interface DesktopBridge {
  getRuntime: () => Promise<RuntimeConfig>;
  pickImage: () => Promise<{ name: string; dataUrl: string } | null>;
  openPath: (target: string) => Promise<boolean>;
  showInFolder: (target: string) => Promise<boolean>;
  restartBackend: () => Promise<RuntimeConfig>;
  checkForUpdates: () => Promise<{ ok: boolean; version?: string | null; message?: string }>;
  downloadUpdate: () => Promise<{ ok: boolean; message?: string }>;
  installUpdate: () => Promise<{ ok: boolean; message?: string }>;
  onUpdateStatus: (callback: (value: UpdateEvent) => void) => () => void;
  minimize: () => Promise<void>;
  toggleMaximize: () => Promise<boolean>;
  close: () => Promise<void>;
  isMaximized: () => Promise<boolean>;
  onRuntimeReady: (callback: (runtime: RuntimeConfig) => void) => () => void;
  onMenuAction: (callback: (action: string) => void) => () => void;
}

declare global {
  interface Window {
    lumen?: DesktopBridge;
  }
}

export {};
