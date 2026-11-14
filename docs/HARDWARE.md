# 硬件与显存指南

## 一句话结论

- **推荐：NVIDIA RTX 3060 12 GB、RTX 4070 / 4070 SUPER 12 GB 或同级显卡，32 GB 内存。**
- 如果显卡上还跑着别的 AI（例如已占用约 10 GB），请使用 **SD-Turbo 512 + 低显存守护**，不要直接上 SDXL 1024。
- 没有独显也能用 CPU 出图，但速度以分钟计；Hybrid/NPU 目前建议通过 ComfyUI 的 OpenVINO / DirectML 后端。

## 配置档位

| 档位 | CPU | 内存 | GPU / 显存 | 典型模型与分辨率 | 预期 |
| --- | --- | --- | --- | --- | --- |
| 最低 | 4 核 | 16 GB | 无独显 / 核显 | SD 1.5 512、SD-Turbo 512 | 1–5 分钟/张，低显存模式 |
| 推荐 | 6 核 | 32 GB | RTX 3060 12 GB / 4070 12 GB / 4070 SUPER 12 GB | SDXL 1024、SD-Turbo 512 | 数秒–数十秒/张 |
| 共用显卡 | 6 核 | 32 GB | 剩余 2–6 GB | SD-Turbo 512 + 顺序卸载 | 较慢，但可与其他 AI 共存 |
| 舒适 | 8 核 | 64 GB | RTX 4080 / 4090 16–24 GB | FLUX、SD 3.5、SDXL 高分辨率 | 更高质量与更大画幅 |

Mac（MPS）与 Linux 未包含在当前安装包中，但后端的 Diffusers 引擎会走 PyTorch 的 `mps`/CPU（需自行调整设备配置与打包）。

## 显存是怎么被用掉的

扩散模型推理的显存主要来自：

1. **UNet / Transformer 权重**：SD-Turbo FP16 约 1–2 GB；SDXL 约 4–6 GB；FLUX 更大。
2. **激活值**：随分辨率平方增长。1024² 的激活远高于 512²。
3. **VAE 解码**：高分辨率时可能出现峰值；VAE 分块可以显著降低。
4. **文本编码器**：SDXL 有两个 CLIP，首次加载时占用更高。
5. **CUDA 上下文与缓存**：PyTorch 会保留缓存；应用在生成后主动清空。
6. **Electron 界面**：约 100–200 MB，远小于模型；可在系统层面关闭硬件加速，但通常不必。

## 低显存守护做了什么

开启后（默认）：

- `enable_attention_slicing("max")`：注意力分块，降低峰值
- `enable_vae_slicing()`：VAE 分块解码
- `enable_vae_tiling()`：大图分块
- `enable_sequential_cpu_offload()`：把子模块按需搬到 GPU，峰值可降到 1–2 GB 量级
- 生成结束：删除 pipeline、`gc.collect()`、`torch.cuda.empty_cache()`、`ipc_collect()`
- 加载前检查 `nvidia-smi` 的空闲显存，低于 650 MB 时直接拒绝，避免驱动崩溃

代价是速度：顺序卸载会频繁在 CPU/GPU 间搬运权重，可能比正常模式慢 2–5 倍。对“显卡还被别的 AI 占着”的场景，这是可接受的交换。

## 不同空闲显存的建议

| 空闲显存 | 建议 |
| --- | --- |
| ≥ 8 GB | SDXL 1024；可尝试 FLUX（仍需注意 12 GB 上限） |
| 4–8 GB | SDXL + 低显存守护，768–1024；或 SD-Turbo 1024 |
| 2–4 GB | SD-Turbo 512；批量 1；关闭其他 AI |
| < 2 GB | SD-Turbo 512 + 顺序卸载，仍可能 OOM；建议先释放显存或用 CPU/云 |
| 0（无 NVIDIA） | CPU 推理，或 ComfyUI 的其他后端 |

应用在「模型」页读取 `nvidia-smi --query-gpu=memory.total,memory.used,memory.free`，每 5 秒刷新。它不会杀死或挂起其他进程。

## 为什么不要一上来选 SDXL 1024

SDXL 的 UNet + 双文本编码器 + 1024² 激活，在只剩 2 GB 时几乎必然 OOM。即使顺序卸载勉强跑通，速度也可能退化到每张数分钟。SD-Turbo 是蒸馏模型，4 步、512²，显存与时间都低一个量级，更适合共存场景。

## NPU

内置 Diffusers 引擎只自动选择 CUDA / CPU，因为：

- PyTorch 对消费级 NPU 的支持仍依赖厂商扩展；
- 不同 NPU 的算子覆盖与精度差异大；
- 直接承诺“支持 NPU”会带来大量不可复现的问题。

可行路径：

- **Intel Core Ultra**：ComfyUI + OpenVINO 自定义节点
- **AMD Ryzen AI**：ComfyUI + DirectML / ONNX Runtime
- **Qualcomm**：ONNX Runtime QNN

这些路径需要在 ComfyUI 侧配置，Lumen 只负责连接。界面会明确标注 NPU 为实验性。

## 性能参考

以下为量级参考，实际取决于模型、步数、分辨率与驱动：

- RTX 4070 SUPER，SD-Turbo 512，4 步：约 1–3 秒（不含首次加载）
- RTX 4070 SUPER，SDXL 1024，28 步：约 8–20 秒
- RTX 4070 SUPER，SDXL 1024，低显存顺序卸载：约 30–90 秒
- 仅剩 2 GB 显存，SD-Turbo 512 顺序卸载：约 20–60 秒
- CPU（16 线程），SD-Turbo 512，4 步：约 1–4 分钟

首次使用还包括模型下载与加载，可能额外数分钟。

## 故障排查

**CUDA out of memory**

1. 关闭其他占用显存的程序（本地 LLM、游戏、浏览器硬件加速）。
2. 开启低显存守护。
3. 长边降到 512，批量设为 1。
4. 换 SD-Turbo。
5. 仍不行：设备切 CPU，或接 ComfyUI/云。

**模型下载失败**

- 配置 `HF_ENDPOINT`（设置或供应商选项）为 `https://hf-mirror.com`。
- 检查磁盘剩余空间（模型缓存可能 10 GB+）。
- gated 模型需要先在 Hugging Face 接受许可。

**生成很慢但没报错**

- 低显存顺序卸载是预期变慢；看「模型」页的显存与模式。
- 检查是否在使用 CPU。
- 首次生成包含模型加载/下载。
