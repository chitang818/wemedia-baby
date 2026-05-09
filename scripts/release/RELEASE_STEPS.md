# 发版步骤（GitHub/Gitee Releases：源码开源 + 闭源安装包发布）

`version.json` 的 **download_url** 固定为 **https://gitee.com/chitangsuper/wemedia-baby/releases**。用户点击「前往下载」会打开该页面，在 releases 中下载 txt 文件后，手动打开 txt 里的链接下载安装包（因安装包超过 Gitee 100MB 限制，不直接上传 exe）。

## 步骤（按需选择要构建的版本）

1. **更新版本号**  
   `python scripts/release/update_version.py set X.Y.Z`

2. **构建安装包**  
   运行“可选择版本”的构建脚本（推荐）：

   ```powershell
   # 只构建 OSS（Fast / PyInstaller）
   .\scripts\release\build_release_matrix.ps1 -DistMode OSS -BuildType Fast

   # 只构建 PRO（Secure / Nuitka）
   .\scripts\release\build_release_matrix.ps1 -DistMode PRO -BuildType Secure

   # 同时构建 PRO + 52POJIE（默认 Auto：PRO/52POJIE 走 Secure）
   .\scripts\release\build_release_matrix.ps1 -DistMode PRO,52POJIE
   ```

   产物示例（依你选择的模式而定）：
   - `dist/installers/WeMediaBaby_Setup_Fast_OSS_vX.Y.Z.exe`
   - `dist/installers/WeMediaBaby_Setup_Secure_PRO_vX.Y.Z.exe`
   - `dist/installers/WeMediaBaby_Setup_Secure_52POJIE_vX.Y.Z.exe`

   先做命令校验（不真正执行构建）：

   ```powershell
   .\scripts\release\build_release_matrix.ps1 -DistMode PRO,52POJIE -DryRun
   ```

3. **上传安装包到可直链的托管**  
   例如：GitHub Releases 附件、蓝奏云等，得到安装包的**直接下载链接**。

4. **Gitee 创建发行版（或同步 GitHub/Gitee Releases）**  
   - 标签：`vX.Y.Z`  
   - 标题 / 说明：按需填写  
   - 若受单文件体积限制：**只上传一个 txt 文件**（如 `download.txt`），内容写**安装包直链**（一行一个链接，可写 3 行分别对应 3 个版本）。  
   - 无需修改 `version.json` 的 `download_url`（保持为 releases 页面）。

5. **推送代码**  
   将本次发版相关改动（如 `version.json` 的 version/notes、CHANGELOG 等）提交并 `git push gitee main`。

用户流程：软件内「检查更新」→ 有更新时「前往下载」→ 打开 Gitee releases 页 → 下载对应版本的 txt → 打开 txt 中的链接 → 下载安装包。
