# 52POJIE（吾爱破解）特别版说明与打包

> 本文说明 **DistMode = `52POJIE`** 的「闭源离线特别版」**产品定位**、**与 Pro 的差异**，以及如何打出安装包。  
> 技术开关定义见 `config/feature_flags.py`，便捷判断方法 `FeatureFlags.is_52pojie()`。  
> `52POJIE` 与 `PRO` 同属 `is_pro_build()`，即安装包侧具备同一套 Pro 能力入口。

---


## 1. 定位（一句话）

52破解特别版**享受 Pro 版本的所有功能**，**无云端服务、无第三方链接、不包含任何推广信息**。面向吾爱破解论坛渠道做品牌化与界面精简。

---

## 2. 与 Pro 版本的主要区别

| 维度 | Pro（`-DistMode PRO`） | 52POJIE 特别版（`-DistMode 52POJIE`） |
|------|------------------------|--------------------------------------|
| **功能范围** | Pro 全部功能 | **与 Pro 完全一致**（`is_pro_build()` 同为 True） |
| **窗口标题** | 「媒小宝」 | **「媒小宝 - 52破解特别版」** |
| **云端 / 账号** | 含登录、订阅、与云端联动的完整闭环 | **无云端**：不含登录/注册/订阅等云端账号体系 |
| **个人中心** | 侧边栏显示「个人中心」入口 | **隐藏**侧边栏「个人中心」（依赖云端账号，故不显示） |
| **软件更新** | 启动时自动检测 + 设置页「检查更新」按钮 | **完全禁用**：启动不检测、设置页无「检查更新」按钮 |
| **设置 · 使用帮助** | 跳转飞书文档教程 | 跳转 **吾爱破解论坛**：<https://www.52pojie.cn/forum.php> |
| **设置 · 反馈** | 「帮助与反馈」跳转 GitHub Issues | **移除**反馈入口（无第三方链接） |
| **工作台公告** | 含「关注公众号」等推广文案 | **专属公告**：欢迎语 + 平台说明，**无任何推广信息** |

### 实现位置速查

| 差异项 | 代码文件 | 判断方式 |
|--------|----------|----------|
| 窗口标题 | `src/ui/main_window.py` `_setup_ui()` | `FeatureFlags.is_52pojie()` |
| 禁用启动更新检测 | `src/ui/main_window.py` `showEvent` | `FeatureFlags.is_52pojie()` |
| 隐藏个人中心 | `src/ui/main_window.py` 导航配置处 | `FeatureFlags.is_52pojie()` |
| 设置页（帮助/更新/反馈） | `src/ui/pages/settings_page.py` `_create_about_group()` | `FeatureFlags.is_52pojie()` |
| 公告栏 | `src/ui/components/announcement_widget.py` | `FeatureFlags.is_52pojie()` |
| 便捷判断方法 | `config/feature_flags.py` `is_52pojie()` | — |

---

## 3. 功能范围（与 Pro 对齐的部分）

- 在 `FeatureFlags` 中，`52POJIE` 与 `PRO` 一样走 **`is_pro_build()`**，因此 **Pro 功能集合在「是否开放」层面与 Pro 构建完全一致**。
- 能力清单的**文字介绍**可对照：`docs/01总文档/1.6完整版（Pro）介绍.md` 第 2 节。

---

## 4. 如何打包特别版

### 4.1 推荐：发版矩阵（可同时打 Pro + 特别版）

在仓库根目录 PowerShell 中：

```powershell
# 同时构建 PRO + 52POJIE（默认 Auto：PRO/52POJIE 走 Secure / Nuitka）
.\scripts\release\build_release_matrix.ps1 -DistMode PRO,52POJIE
```

仅校验命令、不真正构建：

```powershell
.\scripts\release\build_release_matrix.ps1 -DistMode PRO,52POJIE -DryRun
```

步骤说明见：`scripts/release/RELEASE_STEPS.md`。

### 4.2 单独打 52POJIE（Nuitka / 或 Fast）

与 `1.4软件打包实施方案.md` 一致，例如：

```powershell
# Secure（Nuitka）— 发版常用
.\scripts\build\build_nuitka.ps1 -DistMode 52POJIE

# Fast（PyInstaller）— 内部快速验证
.\scripts\build\build_fast.ps1 -DistMode 52POJIE
```

交互入口：`build.bat` → 选择构建类型 → 选择 **DistMode = 52POJIE**。

### 4.3 产物命名

安装包默认落在 `dist/installers/`，命名规则与 DistMode、构建类型、版本号绑定，例如：

- `WeMediaBaby_Setup_Secure_52POJIE_vX.Y.Z.exe`（Secure）
- `WeMediaBaby_Setup_Fast_52POJIE_vX.Y.Z.exe`（Fast）

运行时发行模式由打包写入的 **`config/dist_mode.json`** 与环境变量 **`APP_DIST_MODE`** 共同约定（优先环境变量），详见 `config/feature_flags.py` 注释。

---

## 5. 相关文档索引

| 文档 | 用途 |
|------|------|
| `docs/01总文档/1.4软件打包实施方案.md` | 双轨打包、DistMode 总表、脚本入口 |
| `docs/01总文档/1.6完整版（Pro）介绍.md` | Pro / 52POJIE 发行模式与能力边界 |
| `scripts/release/RELEASE_STEPS.md` | Gitee/GitHub 发版与矩阵构建命令 |
| `docs/新功能规划及方案/新增及优化功能方案总.md` | 当前规划汇总；早期吾爱特别版规划草案已归并到该文档，具体实现以代码与本文为准 |

---

## 6. 注意

- **特别版与 Pro 安装包并存时**，注意 Inno 的 `AppId`、卸载项与用户数据目录，避免误覆盖（以 `installers/inno_setup/setup_script.iss` 为准）。
- **对外说明口径**：特别版仅面向约定渠道分发；若运营策略变更，需同步改文案与构建配置。
- 规划层面的「去云端化、拦截遥测」等若未全部落地，**以当前仓库闭源实现与发版说明为准**，勿仅依赖旧规划文档。
