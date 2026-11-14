# Windows SmartScreen 说明

## 当前情况

这台电脑原来**没有代码签名证书**。证书存储中只有：

- 一个用于本机服务的自签名证书（无代码签名用途）
- 一个 `localhost` 开发证书（仅服务器身份验证）

因此 Lumen Studio 是未签名应用，Windows Defender SmartScreen 会显示：

> Microsoft Defender SmartScreen 阻止了无法识别的应用启动。

## 已做的本地处理

为了便于本机测试，我创建并安装了：

- 证书主题：`CN=Lumen Studio Dev, O=Lumen Studio, C=CN`
- 私钥：当前用户证书存储，可导出
- 信任位置：当前用户「受信任的根证书颁发机构」与「受信任的发布者」
- 签名结果：`Get-AuthenticodeSignature` 显示 **Valid**

但 **SmartScreen 仍然可能拦截**。原因是 SmartScreen 看的是**发布者信誉/云端声誉**，不是“本机是否信任这张证书”。自签名证书只能证明“文件没有被改动”，不能建立 Microsoft 的发布者信誉。

> 自签名证书适合本机测试，不适合公开分发。不要把自己生成的自签名根证书发给用户安装。

## 如何继续运行（本机）

### 方法 A：SmartScreen 对话框

1. 点击「更多信息 / More info」。
2. 点击右下角「仍要运行 / Run anyway」。
3. 只需一次；之后 Windows 可能会记住该文件。

### 方法 B：解除文件锁定

如果文件是从浏览器/聊天软件下载的，可能带有“来自 Internet”的标记：

1. 右键安装包或 `Lumen Studio.exe` → 属性。
2. 底部勾选「解除锁定 / Unblock」→ 应用。
3. 或者 PowerShell：

```powershell
Unblock-File "F:\path\to\Lumen-Studio-Setup-0.1.1.exe"
```

### 方法 C：备用启动器

安装包旁边提供了 `Launch Lumen Studio.cmd`。它通过系统命令启动应用，部分环境下可绕过资源管理器的 SmartScreen 检查：

```text
双击 Launch Lumen Studio.cmd
```

如果仍然被拦截，使用下面的方法 D，或购买正式证书。

### 方法 D：临时关闭「检查应用和文件」（不推荐长期开启）

Windows 11：

1. 设置 → 隐私和安全性 → Windows 安全中心。
2. 应用和浏览器控制 → 基于声誉的保护。
3. 临时关闭「检查应用和文件」。
4. 安装/运行 Lumen Studio。
5. **完成后重新打开**该开关。

这会影响整台电脑的安全防护，只建议在你完全信任该构建时临时使用。

## 真正的长期解决方案

购买 **OV 或 EV 代码签名证书**（Sectigo、DigiCert、SSL.com 等），然后用 electron-builder 签名：

```powershell
$env:CSC_LINK = "C:\secure\lumen.pfx"
$env:CSC_KEY_PASSWORD = "..."
npm run dist
```

- **EV 证书**通常有更好的即时 SmartScreen 信誉。
- **OV 证书**签名后仍可能需要一段时间的下载量来建立声誉。
- 签名后把 `build.win.verifyUpdateCodeSignature` 改回 `true`，并重新生成 `latest.yml`。
- 代码签名不会改变应用功能，但会显示发布者名称，并让自动更新校验更安全。

## 校验下载

在运行前核对 SHA-256，确认文件来自本仓库的 Release：

```powershell
Get-FileHash "Lumen-Studio-Setup-0.1.1.exe" -Algorithm SHA256
```

把结果与 Release 页面的 `SHA256SUMS.txt` 对比。

## 为什么不能“免费彻底解决”

SmartScreen 的“无法识别的应用”是微软的声誉系统，不是简单的本地证书开关。自签名证书无法伪造微软信任的发布者身份；绕过提示只能靠用户手动允许、系统设置，或购买受信任的 CA 证书并积累声誉。
