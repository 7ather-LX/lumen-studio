# Contributing

感谢你愿意改进 Lumen Studio。

## 开发环境

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
npm install
node node_modules\electron\install.js
npm run dev
```

## 提交前检查

```powershell
npm run test:backend
npm run typecheck
npm run build
```

UI 改动请附截图，并尽量在 1480×940 与 1120×720 两种窗口尺寸下检查。

## 代码约定

- Python：类型标注、`from __future__ import annotations`、不要在导入时加载 torch
- TypeScript：strict 模式，无未使用变量
- 新供应商：实现 `BaseEngine` 并在 `engines/registry.py` 注册
- 不要提交 `build/python`、模型权重、API Key、作品图片
- 不要默认上传任何用户数据或加入遥测

## 新引擎清单

- [ ] `availability()` 给出可操作的原因
- [ ] `test_connection()` 不泄露密钥
- [ ] `generate()` 支持取消与进度回调
- [ ] 图生图有明确错误（不支持时）
- [ ] 记录实际输出尺寸
- [ ] 在 `docs/PROVIDERS.md` 增加说明
- [ ] 至少一个后端测试或可复现的手动验证步骤

## 发布

维护者按 `docs/BUILD.md` 更新版本、打标签，GitHub Actions 会生成安装包与 Release。
