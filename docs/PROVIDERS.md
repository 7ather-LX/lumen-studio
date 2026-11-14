# 模型与供应商

## 本地 Diffusers

### 推荐模型

| 模型 | 下载 | 最低显存 | 原生分辨率 | 说明 |
| --- | --- | --- | --- | --- |
| `stabilityai/sd-turbo` | ~2.5 GB | 1.8 GB（低显存） | 512 | 4 步出图，共用显卡首选 |
| `runwayml/stable-diffusion-v1-5` | ~4 GB | 2.2 GB | 512 | 生态最成熟，LoRA 多 |
| `stabilityai/stable-diffusion-xl-base-1.0` | ~7 GB | 3.8 GB（低显存） | 1024 | 细节更好，低显存下慢 |
| `black-forest-labs/FLUX.1-schnell` | ~24 GB | 10 GB | 1024 | 质量高，12 GB 需卸载/量化 |

模型 ID 可以替换为本地 Diffusers 文件夹的绝对路径。首次下载后缓存在 `%APPDATA%\Lumen Studio\models\huggingface`。

### 选项

- **设备**：`auto` / `cuda` / `cpu`。自动优先 CUDA；无 CUDA 时用 CPU。
- **精度**：`auto` / `fp16` / `bf16` / `fp32`。CUDA 默认 FP16；CPU 默认 FP32。
- **生成后释放模型**：低显存模式默认开启。
- **HF 镜像**：例如 `https://hf-mirror.com`。
- **仅本地缓存**：完全离线，禁止下载。

### 常见错误

| 错误 | 处理 |
| --- | --- |
| `local_runtime_missing` | 在「模型」页安装本地引擎，或运行 `scripts\install-local-engine.ps1` |
| `insufficient_vram` | 关闭其他 AI，或改用 SD-Turbo 512 / CPU / ComfyUI |
| `vram_oom` | 开启低显存守护、降低分辨率、减少批量 |
| `model_load_failed` + 401/403 | 模型是 gated，需要先在 Hugging Face 接受许可 |
| 下载很慢 | 配置 HF 镜像；或手动下载后用本地路径 |

## ComfyUI

适用于已经有 ComfyUI 环境、想复用自定义模型/LoRA/节点的用户。

1. 启动 ComfyUI：`python main.py --listen 127.0.0.1 --port 8188`
2. 「模型」→ ComfyUI → 编辑：
   - 地址：`http://127.0.0.1:8188`
   - 模型：留空则使用第一个 checkpoint
   - 超时：首次加载大模型建议 600 秒
3. 点「测试」确认 `/system_stats` 可访问。
4. 点「获取」读取 checkpoint 列表。

应用只提交一个最小工作流，不会改动 ComfyUI 的队列、设置或自定义节点。若你的 ComfyUI 位于反向代理后并使用 Bearer token，在 API Key 中填写。

低显存：ComfyUI 自身支持 `--lowvram` / `--novram`，可在其启动脚本中添加。应用侧只能控制分辨率与批量。

## OpenAI Images

- Base URL：`https://api.openai.com/v1`
- 模型：`gpt-image-1`（推荐）、`dall-e-3`、`dall-e-2`
- 文生图：`/images/generations`
- 图生图：`/images/edits`（DALL·E 3 不支持）
- 尺寸会映射到供应商支持的最接近规格：
  - `gpt-image-1`：1024²、1536×1024、1024×1536
  - `dall-e-3`：1024²、1792×1024、1024×1792
- 实际尺寸会在结果中标注。

## OpenAI 兼容端点

任何实现以下接口的服务都可以接入（SiliconFlow、Together、本地 vLLM 图片网关等）：

```http
POST {base_url}/images/generations
Authorization: Bearer <key>
Content-Type: application/json

{"model":"...","prompt":"...","n":1,"size":"1024x1024","response_format":"b64_json"}
```

图生图使用 `multipart/form-data` 的 `/images/edits`，字段 `image`、`prompt`、`model`、`size`。

Base URL 请包含 `/v1`。没有 API Key 的本地端点可以留空密钥。

## Stability AI

- Base URL：`https://api.stability.ai`
- 文生图：`/v2beta/stable-image/generate/core`
- 图生图：`/v2beta/stable-image/generate/sd3`，`mode=image-to-image`
- 模型：`sd3.5-large`、`sd3.5-medium`、`core`
- 返回 `image/*` 二进制；错误为 JSON。
- 账户余额不足会返回 402，内容策略拦截通常为 403。

## 离线示例

`demo` 供应商不需要网络与模型，生成的是算法抽象画。它只用于：

- 首次启动时预览完整工作流
- 无 GPU / 无网络环境演示
- 自动化测试

它**不是**扩散模型，结果页与供应商卡片都会明确标注。

## 供应商优先级

- 「设为默认」写入数据库，创作台默认选中。
- 设置中的 `default_provider_id` 作为回退。
- 不可用的供应商仍会显示，但会标注原因与解决入口。
