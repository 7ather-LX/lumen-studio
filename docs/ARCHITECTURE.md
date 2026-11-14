# 架构

Lumen Studio 是一个两进程的本地桌面应用：Electron 负责窗口、系统集成与安全边界，Python sidecar 负责生成、存储、分析与学习。两者只通过 `127.0.0.1` 上的 HTTP API 通信。

```text
┌────────────────────────────────────────────────────────────┐
│ Electron main                                              │
│  · BrowserWindow / preload / IPC                           │
│  · 随机端口 + 随机会话 token                                │
│  · 启动、监控、终止 Python sidecar                          │
│  · 打开文件夹 / 选图 / 窗口控制                             │
└───────────────┬────────────────────────────────────────────┘
                │ HTTP 127.0.0.1:<random>  X-Lumen-Token
┌───────────────▼────────────────────────────────────────────┐
│ React renderer (sandboxed, no Node)                         │
│  · 创作台 / 作品库 / 模型 / 学习 / 设置                     │
└───────────────┬────────────────────────────────────────────┘
                │ fetch
┌───────────────▼────────────────────────────────────────────┐
│ FastAPI sidecar                                            │
│  providers ── engines ── jobs ── image store                │
│  SQLite (WAL) · Pillow/NumPy analysis · preference model    │
└───────┬───────────────────────┬────────────────────────────┘
        │                       │
  Diffusers (CUDA/CPU)     ComfyUI / OpenAI / Stability
```

## 进程与生命周期

1. `electron/main.cjs` 启动，申请单实例锁。
2. 选择一个空闲端口（默认从 8765 开始），生成 32 字节 token。
3. 开发模式启动 `.venv` 中的 `uvicorn backend.asgi:app`；打包模式启动 `resources/python/python.exe`。
4. 轮询 `/api/health`，成功后才加载 renderer。
5. renderer 通过 preload 的 `runtime:get` 获取 API 地址与 token；所有请求带 `X-Lumen-Token`。
6. 退出时使用 `taskkill /T /F` 终止整个 Python 进程树。

后端只监听回环地址。即使 token 泄露，攻击面也限于本机；API 没有公网监听选项。

## 数据目录

打包应用使用 Electron `app.getPath("userData")`，即：

```text
%APPDATA%\Lumen Studio\
  lumen.db                 SQLite（WAL）
  settings.json            非敏感设置（原子写入）
  secrets.json             DPAPI 加密的 API Key
  learning_model.json      本地偏好模型
  images\                  PNG 原图
  thumbs\                  WebP 缩略图
  uploads\                 图生图临时参考图
  models\huggingface\      HF 缓存
  logs\backend.log         滚动日志
```

作品 PNG 内嵌 `Lumen.*` 文本元数据；可在设置中关闭。删除作品会同时删除原图、缩略图与反馈行。

## 生成流程

```text
POST /api/generate
  → GenerationService.prepare()
      · 选择/校验 provider
      · resolve_dimensions()：比例、长边、最大像素、16px 对齐
      · 读取空闲显存，决定 low_vram
      · model_defaults() + 用户显式参数
      · LearningService.suggest()（可选）
      · compose_prompt()：风格 + 学习词
      · 解码/加载参考图
  → JobManager 单线程队列
  → Engine.generate()
      · Diffusers / ComfyUI / OpenAI / Stability / Demo
  → ImageStore.save_generated()
      · PNG + WebP
      · analyze_image()
      · 感知哈希查重
      · SQLite 记录
  → job.result.image_ids
```

生成任务串行执行，避免两个大模型同时抢显存。`POST /api/jobs/{id}/cancel` 设置事件；支持在采样回调、轮询循环和批次之间检查。

## 引擎接口

所有引擎实现 `backend/engines/base.py`：

- `availability(provider, secrets)`：是否可用、原因、是否可安装
- `test_connection()`：供应商连接测试
- `list_models()`：ComfyUI checkpoint / OpenAI 模型等
- `generate(context, provider, secrets, progress, cancelled)`：返回 `GeneratedImage[]`

新增引擎只需实现这四件事并在 `registry.py` 注册，前端会自动显示为供应商类型。

### Diffusers 低显存路径

当 `low_vram` 为真或空闲显存低于约 4.5 GB：

1. `pipe.enable_attention_slicing("max")`
2. `pipe.enable_vae_slicing()` / `enable_vae_tiling()`
3. `pipe.enable_sequential_cpu_offload()`（失败时退回 model offload 或 `.to(device)`）
4. 生成结束：清空 pipeline、`gc.collect()`、`torch.cuda.empty_cache()`、`ipc_collect()`
5. 加载前检查空闲显存；低于 650 MB 直接给出可操作错误，不让 CUDA 崩溃

所有 pipeline 只缓存一个，模型按需加载。

### ComfyUI

内置最小工作流：

```text
CheckpointLoaderSimple
  ├─ CLIPTextEncode (positive)
  ├─ CLIPTextEncode (negative)
  └─ KSampler ← EmptyLatentImage 或 VAEEncode(LoadImage)
       └─ VAEDecode → SaveImage
```

通过 `/object_info/CheckpointLoaderSimple` 读取模型列表，`/upload/image` 上传参考图，`/prompt` 排队，`/history/{id}` 轮询，`/view` 下载。

## 图像分析

`services/analysis.py` 在最长边 512 的采样图上计算：

- 拉普拉斯方差 → 清晰度
- 亮度均值/方差 → 曝光、对比度
- HSV 饱和度 + Hasler-Süsstrunk 色彩丰富度
- 64 桶亮度熵
- 边缘重心与左右/上下亮度差 → 构图平衡
- 加权技术质量 0–100
- 6 色主色板、dHash 64 位感知哈希

这些指标是**技术指标**，不是审美判断。审美信号来自用户星级与收藏。

## 偏好学习

`services/learning.py`：

- 114 维特征：9 个连续参数 + 8 provider + 8 model + 12 style + 5 scheduler + 64 token 哈希 + 8 图像指标
- 标签：`(reward + 1) / 2`，reward 由星级映射并对收藏加成
- 权重：`(0.45 + |reward|) * 0.82^(age/30d)`，降低旧反馈影响
- 模型：逻辑回归，L2=0.025，420 轮；≥10 样本时做 4 折交叉验证
- 推荐：在步数 × CFG × 采样器网格上打分，减去偏离模型默认值的惩罚，保留 15% 探索
- 提示词：按 token 出现/不出现的平均 reward 差提取正负相关词，最多 4 正 / 3 负

手动填写的步数、CFG 不会被覆盖；自动调参只填补留空项。所有学习可一键暂停。

## 安全边界

- `contextIsolation: true`、`sandbox: true`、`nodeIntegration: false`
- 生产 CSP 禁止内联脚本与外部连接（除回环 API）
- 自定义协议/外部链接通过 `shell.openExternal`，拒绝窗口内导航
- API token 每次启动随机，前端不落盘
- 路径打开 IPC 限定在数据目录/资源目录内
- 上传图片大小、像素数、格式校验；Pillow 解压炸弹保护
- API Key 使用 DPAPI（Windows）加密；非 Windows 开发环境退化为带标记的 base64

## 打包

`scripts/build-backend.mjs`：

1. 下载 CPython 3.12 embeddable
2. 修改 `python312._pth`，加入 `Lib\site-packages`、资源根目录、`import site`
3. 用宿主 Python 3.12 的 pip 将 `pip` 与 `requirements-core.txt` 安装到 embeddable 的 site-packages
4. 清理缓存，验证 `fastapi/uvicorn/PIL/numpy/pip`
5. electron-builder 将 `build/python` 与 `backend` 放入 `resources/`

PyTorch/Diffusers 不打进安装包，由「模型」页的运行时安装器写入同一个嵌入式 Python，避免安装包膨胀到数 GB。
