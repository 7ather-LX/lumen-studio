# 代码签名证书检查报告

检查时间：2026-11-14  
检查方式：`Cert:\CurrentUser\My`、`Cert:\CurrentUser\Root`、`Cert:\CurrentUser\TrustedPublisher`、`certutil -store My`

## 检查结果

检查前，当前用户的「个人」证书存储中有 2 张证书：

| 主题 | 用途 | 结论 |
| --- | --- | --- |
| `CN=473a89d9-...` | 无 EKU，私钥存在 | 不是代码签名证书 |
| `CN=localhost` | 服务器身份验证 | 不是代码签名证书 |

「受信任的发布者」为空，系统中也没有 `signtool.exe`。

**结论：原机器没有可用的代码签名证书。**

## 已创建的本地测试证书

```text
Subject:     CN=Lumen Studio Dev, O=Lumen Studio, C=CN
Thumbprint:  99E6F1E73759A4873FCE612FF4A48272B979BC77
NotAfter:    2029-11-14
Key:         CurrentUser\My（可导出私钥）
Trusted:     CurrentUser\Root
             CurrentUser\TrustedPublisher
```

导出文件（本机，未提交）：

```text
build/codesign/LumenStudio.pfx
build/codesign/LumenStudio.cer
build/codesign/password.txt
```

这些文件位于 `.gitignore`，不会进入 GitHub。

## 签名结果

```text
release\win-unpacked\Lumen Studio.exe
  Status: Valid
  Publisher: CN=Lumen Studio Dev, O=Lumen Studio, C=CN

release\Lumen-Studio-Setup-0.1.1.exe
  Status: Valid
  Publisher: CN=Lumen Studio Dev, O=Lumen Studio, C=CN
```

`latest.yml` 是在签名之后重新生成的，SHA-512/大小与最终安装包一致。

## 为什么 SmartScreen 仍然拦截

SmartScreen 使用的是 Microsoft 的**发布者声誉**，不是本机证书信任：

- 自签名证书能证明文件未被修改；
- 但它不能证明发布者是 Microsoft 已知/有信誉的软件发行商；
- 新文件即使有效签名，也可能显示“无法识别的应用”。

要稳定消除提示，需要：

1. 购买 OV/EV 代码签名证书；EV 通常有更好的即时信誉。
2. 用正式证书重新打包（`CSC_LINK` / `CSC_KEY_PASSWORD`）。
3. 把 `build.win.verifyUpdateCodeSignature` 改回 `true`。
4. 积累下载量/向 Microsoft 提交文件以建立声誉。

## 继续运行

见 [WINDOWS_SMARTSCREEN.md](WINDOWS_SMARTSCREEN.md) 或安装包旁的 `SMARTSCREEN.txt`：

- SmartScreen 对话框 → 更多信息 → 仍要运行
- 文件属性 → 解除锁定
- 备用启动器 `Launch Lumen Studio.cmd`
- 临时关闭「检查应用和文件」（不推荐长期）

## 删除本地测试证书

如果不再需要本机测试签名：

```powershell
certutil -user -delstore Root 99E6F1E73759A4873FCE612FF4A48272B979BC77
certutil -user -delstore TrustedPublisher 99E6F1E73759A4873FCE612FF4A48272B979BC77
certutil -user -delstore My 99E6F1E73759A4873FCE612FF4A48272B979BC77
```

删除后，已签名文件仍能显示签名，但本机将不再信任该自签名证书。
