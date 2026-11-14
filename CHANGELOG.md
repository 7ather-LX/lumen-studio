# Changelog

## 0.1.0 — 2026-11-14

首个可运行版本。

### 创作

- 文生图 / 图生图
- 1:1、4:3、3:4、3:2、2:3、16:9、9:16、21:9
- 长边 512–2048，16px 对齐，最大像素可配置
- 步数、CFG、种子、采样器、批量 1–4
- 12 种风格预设、提示词增强
- 批量缩略图、收藏、评分、下载、复用参数、以图生图

### 引擎

- 本地 Diffusers（CUDA / CPU），按需安装 PyTorch
- ComfyUI（本机/局域网，checkpoint 发现、参考图上传、历史轮询）
- OpenAI Images（gpt-image-1 / DALL·E）
- Stability AI（core / SD3 图生图）
- OpenAI 兼容端点
- 离线示例引擎

### 低显存

- 实时 `nvidia-smi` 显存监控（5 秒 TTL）
- 顺序 CPU 卸载、注意力切片、VAE 分块
- 生成后释放模型与 CUDA 缓存
- 空闲显存不足时预检并给出可操作错误
- 界面显示总显存/已用/可用与档位建议

### 学习

- 技术质量分析：清晰度、曝光、对比、色彩、构图、熵、主色板、dHash
- 星级/收藏 → 逻辑回归偏好模型（114 维）
- 自动推荐步数/CFG/采样器，保留探索
- 正负提示词偏好提取
- 质量趋势、模型准确率、学习阶段
- 可随时暂停

### 桌面

- Electron 39 + React 19 + Vite
- 随机端口 + 会话 token
- Windows DPAPI 加密 API Key
- NSIS 安装器、桌面快捷方式、卸载器
- 嵌入式 Python 运行时构建脚本
- GitHub Actions Windows 测试/打包/Release
