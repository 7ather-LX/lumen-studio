# Lumen Studio v0.1.1

动漫赛璐珞角色工作流 + 本地 LLM 提示词助手。

## 新增

- **赛璐珞 / 日系插画 / 手绘线稿** 风格，默认使用赛璐珞
- **动漫角色构建器**：人数、发型/发色、眼睛、服装、表情、动作、景别、背景
- **本地 LLM 提示词助手**：OpenAI 兼容端点，把中文角色想法改写成 Danbooru 风格英文 tags 与负向词
- **赛璐珞线条增强** 后处理（可选）
- **Counterfeit V3 / MeinaMix** 动漫模型推荐
- 作品详情：裁切、继续生成、定位原文件、删除
- 设置页 SmartScreen 说明与本地证书签名
- 新桌面图标：由本地 SD-Turbo 图生图生成，深色 + 青柠光圈

## SmartScreen

本构建使用本机自签名证书签名，`Get-AuthenticodeSignature` 显示 Valid；但 SmartScreen 基于发布者声誉，仍可能提示“无法识别的应用”。

在提示中点「更多信息 → 仍要运行」即可。完整说明见 [WINDOWS_SMARTSCREEN.md](https://github.com/7ather-LX/lumen-studio/blob/main/docs/WINDOWS_SMARTSCREEN.md)。

自签名证书不能替代 OV/EV 代码签名证书；正式公开分发建议购买 CA 证书。

## 本地 LLM

设置 → 提示词助手：

```text
http://127.0.0.1:8000/v1
deepseek-v4-pro-qwen3.5-9b-uncensored-heretic
```

API Key 用 Windows DPAPI 加密保存。

## 安装

下载 `Lumen-Studio-Setup-0.1.1.exe`。未签名/自签名构建可能触发 SmartScreen，按上方说明继续。

SHA-256：

```text
2F119F000E5EBD079CA2AC6EFEBD74CCF7E554920D75071CF5F9024AB10AF0B5  Lumen-Studio-Setup-0.1.1.exe
```
