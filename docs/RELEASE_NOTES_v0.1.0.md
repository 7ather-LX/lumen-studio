# Lumen Studio v0.1.0

首个公开版本：一个本地优先的 Windows AI 图像工作室。

## 亮点

- **文生图 / 图生图**，支持 8 种画幅、512–2048 长边、步数/CFG/种子/采样器/批量
- **本地 Diffusers**（CUDA/CPU，按需安装）、**ComfyUI**、**OpenAI Images**、**Stability AI**、OpenAI 兼容端点
- **低显存守护**：实时显存监控、顺序 CPU 卸载、VAE 分块、生成后释放；适合与其他 AI 共用显卡
- **本地学习**：星级/收藏 → 偏好模型 → 自动调参 + 提示词偏好；完全可关闭
- **图像分析**：清晰度、曝光、对比、色彩、构图、主色板、感知哈希
- **桌面集成**：NSIS 安装器、桌面快捷方式、开始菜单、卸载器
- **隐私**：无遥测、API Key 使用 Windows DPAPI 加密、后端仅监听 127.0.0.1

## 安装

下载 `Lumen-Studio-Setup-0.1.0.exe`，双击安装。首次使用真实本地生成时，在「模型」页安装 PyTorch + Diffusers。

**推荐硬件：** RTX 3060 12 GB / RTX 4070 / 4070 SUPER 12 GB 或同级，32 GB 内存。  
**共用显卡：** 若其他 AI 已占用约 10 GB，请使用 SD-Turbo 512 + 低显存守护。

## 已知限制

- Windows x64 only
- 安装包未签名，可能触发 SmartScreen；请核对 SHA-256
- 当前学习为偏好排序，不微调模型权重
- NPU 需通过 ComfyUI/OpenVINO，实验性
- 云端尺寸会映射到供应商支持的最接近规格

## 校验

```text
F97B741E293AD821E937557FB4CF86475C9AD93D839631B86E06193BE0D7B8DB  Lumen-Studio-Setup-0.1.0.exe
```

构建时间：2026-11-14
