"use strict";

const { app, BrowserWindow, Menu, dialog, ipcMain, session, shell } = require("electron");
const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const fsp = require("node:fs/promises");
const net = require("node:net");
const path = require("node:path");

const APP_NAME = "Lumen Studio";
const DEV_URL = "http://127.0.0.1:5173";
const isDev = !app.isPackaged;

app.setName(APP_NAME);
app.setAppUserModelId("studio.lumen.app");

let mainWindow = null;
let backendProcess = null;
let backendPort = 0;
let backendToken = "";
let backendLog = null;
let backendStarting = null;
let isQuitting = false;
let boundsFile = null;

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

function projectRoot() {
  return path.resolve(__dirname, "..");
}

function resourcesRoot() {
  return app.isPackaged ? process.resourcesPath : projectRoot();
}

function dataRoot() {
  return app.getPath("userData");
}

async function findFreePort(start = 8765) {
  for (let port = start; port < start + 50; port += 1) {
    const available = await new Promise((resolve) => {
      const probe = net.createServer();
      probe.unref();
      probe.once("error", () => resolve(false));
      probe.listen(port, "127.0.0.1", () => {
        probe.close(() => resolve(true));
      });
    });
    if (available) return port;
  }
  throw new Error("找不到可用的本地端口");
}

function openLogFile() {
  const logDir = path.join(dataRoot(), "logs");
  fs.mkdirSync(logDir, { recursive: true });
  const logPath = path.join(logDir, "backend.log");
  try {
    if (fs.existsSync(logPath) && fs.statSync(logPath).size > 4 * 1024 * 1024) {
      fs.renameSync(logPath, path.join(logDir, "backend.old.log"));
    }
  } catch {
    /* logging must never block startup */
  }
  backendLog = fs.createWriteStream(logPath, { flags: "a" });
  backendLog.write(`\n\n=== ${new Date().toISOString()} Lumen Studio ${app.getVersion()} ===\n`);
  return logPath;
}

function backendLaunch() {
  const root = projectRoot();
  if (!app.isPackaged) {
    const configured = process.env.LUMEN_PYTHON;
    const venvPython = path.join(root, ".venv", "Scripts", "python.exe");
    const python = configured || (fs.existsSync(venvPython) ? venvPython : "python");
    return {
      command: python,
      args: ["-m", "uvicorn", "backend.asgi:app", "--host", "127.0.0.1", "--port", String(backendPort)],
      cwd: root,
      shell: false,
    };
  }
  const python = path.join(resourcesRoot(), "python", "python.exe");
  return {
    command: python,
    args: ["-m", "uvicorn", "backend.asgi:app", "--host", "127.0.0.1", "--port", String(backendPort)],
    cwd: resourcesRoot(),
    shell: false,
  };
}

async function startBackend() {
  if (backendStarting) return backendStarting;
  backendStarting = (async () => {
    backendPort = await findFreePort(Number(process.env.LUMEN_PORT) || 8765);
    backendToken = crypto.randomBytes(32).toString("hex");
    const logPath = openLogFile();
    const launch = backendLaunch();
    backendLog.write(`launch: ${launch.command} ${launch.args.join(" ")}\n`);

    if (!fs.existsSync(launch.command) && launch.command !== "python") {
      throw new Error(`Python 运行时不存在：${launch.command}`);
    }

    backendProcess = spawn(launch.command, launch.args, {
      cwd: launch.cwd,
      shell: launch.shell,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8",
        LUMEN_TOKEN: backendToken,
        LUMEN_DATA_DIR: dataRoot(),
        LUMEN_DEV: isDev ? "1" : "0",
        LUMEN_RESOURCES_DIR: resourcesRoot(),
        LUMEN_VERSION: app.getVersion(),
        HF_HOME: path.join(dataRoot(), "models", "huggingface"),
        HF_HUB_CACHE: path.join(dataRoot(), "models", "huggingface", "hub"),
        TORCH_HOME: path.join(dataRoot(), "models", "torch"),
        XDG_CACHE_HOME: path.join(dataRoot(), "cache"),
      },
    });

    backendProcess.stdout.on("data", (chunk) => backendLog?.write(chunk));
    backendProcess.stderr.on("data", (chunk) => backendLog?.write(chunk));
    backendProcess.on("exit", (code, signal) => {
      backendLog?.write(`backend exited code=${code} signal=${signal}\n`);
      backendProcess = null;
    });

    const api = `http://127.0.0.1:${backendPort}`;
    const deadline = Date.now() + 90_000;
    let lastError = "启动超时";
    while (Date.now() < deadline) {
      if (!backendProcess) throw new Error(`后端进程提前退出，请查看日志：${logPath}`);
      try {
        const res = await fetch(`${api}/api/health`, {
          headers: { "X-Lumen-Token": backendToken },
          signal: AbortSignal.timeout(2000),
        });
        if (res.ok) {
          const health = await res.json();
          if (health.status === "ok") return { api, token: backendToken, logPath };
        }
        lastError = `健康检查返回 ${res.status}`;
      } catch (error) {
        lastError = error?.message || String(error);
      }
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
    throw new Error(`${lastError}。日志：${logPath}`);
  })();
  try {
    return await backendStarting;
  } finally {
    backendStarting = null;
  }
}

async function stopBackend() {
  if (!backendProcess) return;
  const pid = backendProcess.pid;
  backendProcess = null;
  if (process.platform === "win32") {
    await new Promise((resolve) => {
      const killer = spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { windowsHide: true });
      killer.once("exit", resolve);
      killer.once("error", resolve);
    });
  } else {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      /* already gone */
    }
  }
}

function loadWindowState() {
  boundsFile = path.join(dataRoot(), "window-state.json");
  try {
    const parsed = JSON.parse(fs.readFileSync(boundsFile, "utf8"));
    if (Number.isFinite(parsed.width) && Number.isFinite(parsed.height)) return parsed;
  } catch {
    /* first run */
  }
  return { width: 1480, height: 940 };
}

function saveWindowState() {
  if (!mainWindow || !boundsFile) return;
  try {
    const bounds = mainWindow.getNormalBounds();
    fs.writeFileSync(boundsFile, JSON.stringify({ ...bounds, maximized: mainWindow.isMaximized() }));
  } catch {
    /* ignore */
  }
}

function errorPage(message) {
  const safe = String(message).replace(/[<>&"]/g, (char) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" })[char]);
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    body{margin:0;height:100vh;display:grid;place-items:center;background:#0b0c10;color:#e8eaf2;font-family:'Segoe UI',sans-serif}
    .box{max-width:620px;padding:38px;border:1px solid #2a2d38;border-radius:20px;background:#12141b;box-shadow:0 24px 80px #0008}
    h1{font-size:20px;margin:0 0 12px}p{color:#9aa0b4;line-height:1.7;white-space:pre-wrap;font-size:13px}
    button{margin-top:18px;background:#c9f27c;color:#10130c;border:0;border-radius:10px;padding:10px 18px;font-weight:600;cursor:pointer}
  </style></head><body><div class="box"><h1>本地服务未能启动</h1>
  <p>${safe}</p><p>请确认安装完整，或打开日志查看详细信息。</p>
  <button onclick="window.lumen && window.lumen.restartBackend().then(function(){location.reload()}).catch(function(){})">重新启动本地服务</button></div></body></html>`;
  return "data:text/html;charset=utf-8," + encodeURIComponent(html);
}

async function createWindow() {
  const state = loadWindowState();
  mainWindow = new BrowserWindow({
    width: state.width || 1480,
    height: state.height || 940,
    x: state.x,
    y: state.y,
    minWidth: 1120,
    minHeight: 720,
    show: false,
    frame: false,
    backgroundColor: "#0b0c10",
    title: APP_NAME,
    icon: fs.existsSync(path.join(projectRoot(), "build", "icon.ico"))
      ? path.join(projectRoot(), "build", "icon.ico")
      : undefined,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });

  mainWindow.once("ready-to-show", () => {
    if (state.maximized) mainWindow.maximize();
    mainWindow.show();
  });

  mainWindow.on("resize", saveWindowState);
  mainWindow.on("move", saveWindowState);
  mainWindow.on("close", saveWindowState);
  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    const allowed = isDev ? url.startsWith(DEV_URL) : url.startsWith("file:");
    if (!allowed) {
      event.preventDefault();
      if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    }
  });

  try {
    const runtime = await startBackend();
    if (isDev) {
      await mainWindow.loadURL(DEV_URL);
    } else {
      await mainWindow.loadFile(path.join(projectRoot(), "dist", "index.html"));
    }
    mainWindow.webContents.send("runtime:ready", {
      ...runtime,
      version: app.getVersion(),
      dataDir: dataRoot(),
      resourcesDir: resourcesRoot(),
      isPackaged: app.isPackaged,
    });
    if (isDev && process.env.LUMEN_DEVTOOLS === "1") mainWindow.webContents.openDevTools({ mode: "detach" });
    if (process.env.LUMEN_SMOKE === "1") runSmokeCapture();
  } catch (error) {
    await mainWindow.loadURL(errorPage(error?.message || String(error)));
  }
}

async function runSmokeCapture() {
  const out = process.env.LUMEN_SMOKE_OUT || path.join(projectRoot(), "build", "smoke.png");
  try {
    await new Promise((resolve) => setTimeout(resolve, Number(process.env.LUMEN_SMOKE_DELAY) || 5000));
    const image = await mainWindow.webContents.capturePage();
    await fsp.mkdir(path.dirname(out), { recursive: true });
    await fsp.writeFile(out, image.toPNG());
    console.log(`SMOKE_SCREENSHOT=${out}`);
  } catch (error) {
    console.error("SMOKE_FAILED", error);
  } finally {
    setTimeout(() => app.quit(), 300);
  }
}

function registerIpc() {
  ipcMain.handle("runtime:get", () => ({
    api: backendPort ? `http://127.0.0.1:${backendPort}` : null,
    token: backendToken || null,
    version: app.getVersion(),
    dataDir: dataRoot(),
    resourcesDir: resourcesRoot(),
    isPackaged: app.isPackaged,
    platform: process.platform,
  }));

  ipcMain.handle("dialog:pick-image", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "选择参考图片",
      properties: ["openFile"],
      filters: [{ name: "图片", extensions: ["png", "jpg", "jpeg", "webp", "bmp"] }],
    });
    if (result.canceled || !result.filePaths[0]) return null;
    const filePath = result.filePaths[0];
    const stat = await fsp.stat(filePath);
    if (stat.size > 25 * 1024 * 1024) throw new Error("图片不能超过 25 MB");
    const ext = path.extname(filePath).slice(1).toLowerCase();
    const mime = ext === "jpg" || ext === "jpeg" ? "image/jpeg" : `image/${ext}`;
    const bytes = await fsp.readFile(filePath);
    return { name: path.basename(filePath), dataUrl: `data:${mime};base64,${bytes.toString("base64")}` };
  });

  ipcMain.handle("path:open", async (_event, target) => {
    if (typeof target !== "string" || !target) throw new Error("无效路径");
    const resolved = path.resolve(target);
    const allowedRoots = [dataRoot(), resourcesRoot(), app.getPath("logs")];
    if (!allowedRoots.some((root) => resolved === root || resolved.startsWith(root + path.sep))) {
      throw new Error("只能打开应用数据目录中的路径");
    }
    const error = await shell.openPath(resolved);
    if (error) throw new Error(error);
    return true;
  });

  ipcMain.handle("path:show", (_event, target) => {
    if (typeof target !== "string" || !target) return false;
    const resolved = path.resolve(target);
    if (![dataRoot(), resourcesRoot()].some((root) => resolved === root || resolved.startsWith(root + path.sep))) return false;
    shell.showItemInFolder(resolved);
    return true;
  });

  ipcMain.handle("app:restart-backend", async () => {
    try {
      if (backendPort && backendToken) {
        await fetch(`http://127.0.0.1:${backendPort}/api/shutdown`, {
          method: "POST",
          headers: { "X-Lumen-Token": backendToken },
        }).catch(() => {});
      }
      await stopBackend();
      await new Promise((resolve) => setTimeout(resolve, 350));
      const runtime = await startBackend();
      return { ...runtime, version: app.getVersion(), dataDir: dataRoot(), resourcesDir: resourcesRoot(), isPackaged: app.isPackaged };
    } catch (error) {
      throw new Error(error?.message || String(error));
    }
  });

  ipcMain.handle("window:minimize", () => mainWindow?.minimize());
  ipcMain.handle("window:toggle-maximize", () => {
    if (!mainWindow) return false;
    if (mainWindow.isMaximized()) mainWindow.unmaximize();
    else mainWindow.maximize();
    return mainWindow.isMaximized();
  });
  ipcMain.handle("window:close", () => mainWindow?.close());
  ipcMain.handle("window:is-maximized", () => mainWindow?.isMaximized() || false);
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  registerIpc();
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    const devCsp = [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval' http://127.0.0.1:5173",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: http://127.0.0.1:*",
      "font-src 'self' data:",
      "connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*",
    ].join("; ");
    const prodCsp = [
      "default-src 'self'",
      "script-src 'self'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: http://127.0.0.1:*",
      "font-src 'self' data:",
      "connect-src 'self' http://127.0.0.1:*",
    ].join("; ");
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [isDev ? devCsp : prodCsp],
      },
    });
  });
  await createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", async (event) => {
  if (isQuitting) return;
  event.preventDefault();
  isQuitting = true;
  saveWindowState();
  await stopBackend();
  app.quit();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
