# Security Policy

## 报告漏洞

请通过 GitHub Security Advisory 私下报告，不要先公开 Issue。请包含：

- 影响版本
- 复现步骤
- 影响范围（本地数据、密钥、远程代码执行等）
- 建议的修复方向

我们会在 7 天内确认，并在修复后致谢（除非你希望匿名）。

## 安全设计

- 后端只绑定 `127.0.0.1`，不提供公网监听。
- 每次启动生成新的 256 位会话 token；所有 `/api/*`（包括图片文件与导出）都校验 token。
- Electron：`contextIsolation`、`sandbox`、禁用 `nodeIntegration`、生产 CSP、导航拦截。
- IPC 的路径打开限制在应用数据目录/资源目录内。
- API Key 使用 Windows DPAPI（`CryptProtectData`）按当前用户加密；前端只收到掩码。
- 上传图片限制大小、像素数与格式；Pillow 解压炸弹保护。
- 不包含遥测、崩溃上报、自动更新上传。
- 只有用户主动选择云端供应商时，提示词/参考图才会发往对应服务。

## 已知边界

- 能访问本机回环端口的恶意程序仍可能读取本地数据；这是所有本地桌面应用的共同边界。
- 云端供应商由其自身安全与内容政策约束。
- 用户自行填写的本地模型路径/ComfyUI 地址会被信任；不要连接不可信服务。
- 未签名安装包无法证明发布者身份，请核对 SHA-256。

## 依赖

- Python：FastAPI、Uvicorn、httpx、Pydantic、Pillow、NumPy
- 可选：PyTorch、Diffusers、Transformers、Accelerate
- Node：Electron、React、Vite、lucide-react

建议使用 `npm audit` 与 `pip-audit` 定期检查。
