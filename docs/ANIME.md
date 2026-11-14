# 动漫赛璐珞角色工作流

Lumen Studio 现在把“动漫角色 + 手绘赛璐珞”作为一等目标，而不是通用风景生成器。

## 推荐流程

1. 引擎：本地 Diffusers（SD 1.5 动漫模型，低显存）或 ComfyUI（任意动漫 checkpoint/LoRA）。
2. 风格：**赛璐珞**。
3. 角色设定：人数、发型/发色、眼睛、服装、表情、动作、景别、背景。
4. 点「加入提示词」，再点「LLM 完善」交给本地对话模型改写为 booru 风格 tags。
5. 开启「赛璐珞线条增强」（可选，本地后处理）。
6. 512×512 或 768×768 出图；角色全身/半身优先。

## 风格预设

| 风格 | 用途 |
| --- | --- |
| 赛璐珞 | 手绘 2D 动画、平涂、清晰墨线、有限色板 |
| 日系插画 | 现代 anime illustration、细节眼睛、动态光 |
| 手绘线稿 | 角色设计草图、铅笔线、单色 |
| 动画 | 通用 anime key visual |

「赛璐珞」自带的正向词包括：

```text
hand-drawn anime cel shading, bold clean lineart, flat colors,
limited palette, soft cel shadows, expressive detailed eyes,
2D animation key visual, detailed background, masterpiece, best quality
```

负向词覆盖 3D/CGI、写实皮肤、脏线、多余手指、水印与 JPEG 伪影。

## 角色构建器

生成的是 Danbooru 风格 tag，例如：

```text
1girl, silver long hair, red eyes, black sailor suit, gentle smile,
looking at viewer, upper body, cherry blossoms, cel shading, clean lineart
```

这是 Stable Diffusion 1.5 动漫模型最熟悉的语法。中文描述可以先写，再让本地 LLM 转成英文 tags。

## 动漫模型推荐

| 模型 | 类型 | 显存 | 说明 |
| --- | --- | --- | --- |
| `gsdf/Counterfeit-V3.0` | SD 1.5 | 2.2 GB+ | 经典赛璐珞动漫模型 |
| `Meina/MeinaMix` | SD 1.5 | 2.2 GB+ | 日系角色、柔和色彩 |
| `stabilityai/sd-turbo` | SD 2.1 Turbo | 1.8 GB+ | 快速预览；不是专门动漫模型 |
| `stabilityai/stable-diffusion-xl-base-1.0` | SDXL | 3.8 GB+ | 通用高分辨率；动漫需搭配风格/LoRA |

在「模型」页把本地模型 ID 换成上述任一模型即可。首次下载约 4 GB。

## 本地 LLM 提示词助手

支持任意 OpenAI 兼容 `/chat/completions` 端点，例如本机的：

```text
http://127.0.0.1:8000/v1
```

在设置页填写地址、模型 ID 与 API Key，点「测试连接」。创作台的按钮会变为「LLM 完善」，把中文角色想法改写为带角色特征、构图、光线、赛璐珞质量词的英文 tags。

系统提示词明确要求：

- 输出 JSON `{prompt, negative_prompt}`
- 保持角色数量、服装、意图
- 追加 booru 风格 tag
- 过滤 3D/CGI、写实皮肤、坏手、水印
- 不生成色情内容、不涉及未成年人性化场景

密钥用 Windows DPAPI 加密保存在本机，不进入仓库。

## 关于 SafeBooru / Danbooru 学习

Lumen 使用 booru 的**标签语法与安全标签先验**来构建角色构建器和 LLM 提示词，而不是下载或训练版权图片。

- 不随应用分发任何 booru 图片。
- 不在后台上传用户图片或提示词。
- 若你自行下载参考图，请遵守来源网站的条款、版权与 `rating:safe` 过滤。
- 角色构建器只使用通用描述 tag（发色、眼睛、服装、表情、构图），不包含具体作品角色名。

要进一步提升角色一致性，推荐使用动漫 checkpoint + 角色 LoRA，并在 ComfyUI 中固定 seed、构图与 LoRA 权重。

## 赛璐珞后处理

「赛璐珞线条增强」是本地可选的 PIL 后处理：

- 色阶压缩（posterize）→ 平涂感
- 边缘检测 + 半透明墨线 → 手绘线稿感
- 轻微提高饱和度

它不会替代动漫模型。对写实图像可能过度风格化；对动漫 checkpoint 效果更自然。默认关闭。

## 一致性建议

1. 固定 seed 与角色设定。
2. 使用相同的 checkpoint / LoRA。
3. 半身像比全身更容易稳定五官。
4. 用「继续生成」把满意图作为图生图参考，强度 0.35–0.55。
5. 给作品评分，偏好模型会学习你的角色风格参数。
