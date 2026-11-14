# 发布检查清单

在把仓库公开到 GitHub 前：

- [ ] 把 `package.json` 的 `repository.url` 改成真实地址
- [ ] 把 `src/pages/SettingsPage.tsx` 的「项目主页」链接改成真实地址
- [x] GitHub 用户名已设为 `7ather-LX`
- [ ] 确认 `docs/screenshots/` 为最终截图，不含个人信息/API Key
- [ ] `git status` 中没有 `build/python`、`.devdata`、模型、API Key
- [ ] 运行 `npm run test:backend`、`npm run typecheck`、`npm run build`
- [ ] 运行 `npm run dist`，在本机静默安装并验证桌面快捷方式/卸载
- [ ] 在真实显卡上跑一次 SD-Turbo 512 与 SDXL 1024，确认低显存模式
- [ ] 在无 GPU 机器上确认 CPU 模式错误提示可理解
- [ ] 验证 ComfyUI、OpenAI、Stability 至少各一次（或标注未验证）
- [ ] 生成 `SHA256SUMS.txt` 并写入 Release 说明
- [ ] 阅读第三方模型许可证（SDXL / FLUX / Stability / OpenAI）

版本发布：

```powershell
# 同步版本号
# package.json / backend/__init__.py / CHANGELOG.md
git add .
git commit -m "release: v0.1.1"
git tag v0.1.1
git push origin main --tags
```

GitHub Actions 会在 Windows runner 上：

1. 运行 13 个 pytest
2. TypeScript 检查与 Vite 构建
3. 构建嵌入式 Python 运行时
4. 生成 NSIS 安装包
5. 上传 artifact
6. 标签构建自动创建 Release 与 SHA-256

## 人工验收清单

- [ ] 安装器无需管理员即可安装
- [ ] 桌面出现 `Lumen Studio` 快捷方式
- [ ] 开始菜单出现条目
- [ ] 首次启动显示离线示例引擎与硬件信息
- [ ] 「模型」页可安装本地引擎，进度与日志可见
- [ ] 本地生成后显存回落正常
- [ ] 作品保存在 `%APPDATA%\Lumen Studio\images`
- [ ] 评分后「学习」页出现反馈与建议
- [ ] 卸载后作品仍在
- [ ] 重装后作品、设置、密钥仍可读
- [ ] 关闭窗口后 Python 进程退出（任务管理器确认）
