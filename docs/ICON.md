# 应用图标

图标由 Lumen Studio 自身的本地 SD-Turbo 生成，再用 Pillow 做圆角与多尺寸打包，保持应用内的深色 + 青柠色光圈视觉。

## 生成方式

- 引擎：本地 Diffusers / `stabilityai/sd-turbo`
- 模式：图生图（以旧版太阳光圈图标为初始图，强度 0.58）
- 尺寸：512×512，4 步，CFG 0
- 提示词：

```text
minimalist premium app icon, dark obsidian rounded square,
a luminous lime-green sun aperture symbol, thin concentric ring,
one small teal accent dot, flat vector, crisp geometry, centered,
soft inner glow, no text, no letters, high contrast, professional software logo
```

- 负向词：

```text
text, letters, typography, words, photorealistic, 3d, clutter,
detailed background, watermark, multiple symbols, noise, blurry
```

生成四个候选后选择最清晰的一张，做 1024 圆角透明化、锐化与 16–256 多尺寸 ICO。

## 文件

- `build/icon-generated.png`：生成后处理原图
- `build/icon.png`：1024 PNG
- `build/icon.ico`：Windows 多尺寸图标
- `public/icon.png`：网页 favicon
- `scripts/generate-icon.py`：复现脚本

生成脚本使用本地 API，不会把提示词或图片上传到云端。
