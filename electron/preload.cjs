"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("lumen", {
  getRuntime: () => ipcRenderer.invoke("runtime:get"),
  pickImage: () => ipcRenderer.invoke("dialog:pick-image"),
  openPath: (target) => ipcRenderer.invoke("path:open", target),
  showInFolder: (target) => ipcRenderer.invoke("path:show", target),
  restartBackend: () => ipcRenderer.invoke("app:restart-backend"),
  minimize: () => ipcRenderer.invoke("window:minimize"),
  toggleMaximize: () => ipcRenderer.invoke("window:toggle-maximize"),
  close: () => ipcRenderer.invoke("window:close"),
  isMaximized: () => ipcRenderer.invoke("window:is-maximized"),
  onRuntimeReady: (callback) => {
    const listener = (_event, runtime) => callback(runtime);
    ipcRenderer.on("runtime:ready", listener);
    return () => ipcRenderer.removeListener("runtime:ready", listener);
  },
  onMenuAction: (callback) => {
    const listener = (_event, action) => callback(action);
    ipcRenderer.on("menu:action", listener);
    return () => ipcRenderer.removeListener("menu:action", listener);
  },
});
