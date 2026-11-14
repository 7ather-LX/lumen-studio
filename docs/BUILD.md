# 构建与发布

## 前置

- Windows 10/11 x64
- Python **3.12**（构建嵌入式运行时要求宿主也是 3.12）
- Node.js 22+
- npm 或 pnpm

## 开发构建

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
npm install
node node_modules\electron\install.js
npm run dev
```

`npm run dev` 会启动 Vite，并通过 Electron 启动 `.venv` 的 FastAPI。Electron 主进程会等待 `/api/health` 后再显示窗口。

## 安装包

```powershell
npm run dist
```

实际执行：

1. `tsc --noEmit && vite build` → `dist/`
2. `node scripts/build-backend.mjs` → `build/python/`
3. `electron-builder --win nsis` → `release/Lumen-Studio-Setup-0.1.0.exe`

### 嵌入式 Python

`scripts/build-backend.mjs`：

- 从 python.org 下载 `python-3.12.10-embed-amd64.zip`（可用 `LUMEN_PYTHON_EMBED_URL` 覆盖；失败时尝试 npmmirror）
- 解压到 `build/python`
- 改写 `python312._pth`，启用 `site` 与 `Lib\site-packages`，把 `..` 加入模块路径
- 用宿主 Python 3.12 的 pip 将 `pip` + `backend/requirements-core.txt` 安装到嵌入运行时的 `Lib\site-packages`
- 验证 `fastapi / uvicorn / httpx / pydantic / PIL / numpy / pip`
- 清理 `__pycache__`

可用环境变量：

| 变量 | 作用 |
| --- | --- |
| `LUMEN_PYTHON_VERSION` | 默认 `3.12.10` |
| `LUMEN_PYTHON_EMBED_URL` | 自定义 embeddable 下载地址 |
| `LUMEN_HOST_PYTHON` | 指定宿主 Python 3.12 |
| `LUMEN_PIP_INDEX` | pip 索引，例如清华镜像 |
| `LUMEN_SKIP_BACKEND_BUILD=1` | 跳过运行时构建 |

### 安装器行为

electron-builder 的 NSIS 配置：

- `perMachine: false`：当前用户安装，通常无需 UAC
- `allowToChangeInstallationDirectory: true`
- `createDesktopShortcut: true`
- `createStartMenuShortcut: true`
- `deleteAppDataOnUninstall: false`：卸载默认保留作品与设置

卸载入口会出现在 Windows「设置 → 应用」和开始菜单。

## 代码签名

未签名安装包会触发 SmartScreen。正式发布建议购买代码签名证书，并在构建环境设置：

```powershell
$env:CSC_LINK = "C:\path\to\certificate.pfx"
$env:CSC_KEY_PASSWORD = "..."
npm run dist
```

也可使用 Azure Trusted Signing / SignPath 等 CI 签名服务。electron-builder 会自动读取 `CSC_LINK`。

## GitHub Actions

`.github/workflows/build.yml`：

- `test` job：Windows runner，安装 Python/Node 依赖，运行 pytest、TypeScript 检查、Vite 构建
- `package` job：构建嵌入式 Python 与 NSIS 安装包，上传 artifact
- 推送 `v*` 标签时创建 GitHub Release，附安装包与 SHA-256

发布步骤：

```powershell
# 1. 更新 package.json / backend/__init__.py / CHANGELOG
npm version patch --no-git-tag-version
git add .
git commit -m "release: v0.1.1"
git tag v0.1.1
git push origin main --tags
```

工作流需要 `permissions: contents: write`（已配置）。

## 校验安装包

```powershell
Get-FileHash .\release\Lumen-Studio-Setup-0.1.0.exe -Algorithm SHA256
Get-AuthenticodeSignature .\release\Lumen-Studio-Setup-0.1.0.exe
```

把 SHA-256 写入 Release 说明。用户可在下载后自行核对。

## 目录产物

```text
release/
  Lumen-Studio-Setup-0.1.0.exe
  win-unpacked/            # --dir 模式的未安装目录
  builder-effective-config.yaml
build/
  python/                  # 嵌入式运行时（不提交）
  icon.ico
```

`build/python`、`release/`、`node_modules/`、`dist/` 均在 `.gitignore` 中。

## 常见打包问题

- **`build/python` 不存在**：先运行 `npm run build:runtime`。
- **pip 下载失败**：设置 `LUMEN_PIP_INDEX`，或在 CI 中使用默认 PyPI。
- **嵌入 Python 导入失败**：检查 `python312._pth` 是否包含 `Lib\site-packages` 和 `import site`。
- **安装包过大**：确认没有把 `torch`、模型缓存打进 `build/python`。PyTorch 应在用户机器上按需安装。
- **卸载后数据仍在**：这是默认行为，避免误删作品；彻底清除需删除 `%APPDATA%\Lumen Studio`。
