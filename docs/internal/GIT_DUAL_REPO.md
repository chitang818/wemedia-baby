# Git 双仓库协作说明（私有主仓 + 公开开源）

本项目使用**同一个本地文件夹**，对应两个 GitHub 远程仓库：

| 远程名 | 仓库 | 用途 |
|--------|------|------|
| `origin` | [wemedia-baby-Pro](https://github.com/chitang818/wemedia-baby-Pro)（私有） | **主仓**：日常开发、备份，含开源 + 闭源代码 |
| `public` | [wemedia-baby](https://github.com/chitang818/wemedia-baby)（公开） | **开源镜像**：仅含开源部分，由脚本同步 |

## 日常开发（推私有主仓）

```powershell
git add .
git commit -m "你的提交说明"
git push origin main
```

## 更新公开开源仓（推荐）

在 **main 已提交、工作区干净**（`git status` 无未提交文件）时：

- 双击 `scripts/git/publish_oss_to_public.bat`，或
- 在项目根目录执行：`.\scripts\git\publish_oss_to_public.ps1`

仅试跑、不推送：`.\scripts\git\publish_oss_to_public.ps1 -DryRun`

脚本会：

1. 在临时目录 `.git/oss-public-sync` 从 `main` 生成 `oss-release` 快照；
2. 去掉 `docs/`、`src/proprietary/`、`src/plugins/pro/`、`src/pro_features/`；
3. **校验**快照中不含上述路径后，推送到公开仓 `main`；
4. **不改动**你当前工作区的 `main` 与闭源文件。

## 为什么不能 `git push public main`？

| 命令 | 推上去的内容 |
|------|----------------|
| `git push origin main` | 完整版（开源 + 闭源）→ 私有仓，**正确** |
| `git push public main` | 同样把**完整版 main** 推到公开仓 → **闭源会暴露** |
| 运行 `publish_oss_to_public` | 先去掉闭源再推 → **正确** |

本地 `main` 在私有主仓方案里代表**完整项目**；公开仓只应接收脚本生成的**开源快照**。

## 防误推钩子（建议安装一次）

```powershell
.\scripts\git\install_git_hooks.ps1
```

安装后，**任何**对 `public` 的手动 `git push` 都会被拒绝（Windows 下 Git 钩子无法区分分支，故统一拦截）；只有运行 `publish_oss_to_public` 脚本时才会临时放行。

## 禁止操作

- **不要** `git push public main`。
- **不要**提交 `config/auth_config.json`、`config/dist_mode.json`、`.env` 到任一仓库。

## 查看远程配置

```powershell
git remote -v
```

预期：`origin` → `wemedia-baby-Pro`，`public` → `wemedia-baby`。
