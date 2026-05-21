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

## 更新公开开源仓

在**工作区已提交干净**（`git status` 无未提交文件）时执行：

```powershell
.\scripts\git\publish_oss_to_public.ps1
```

或双击 `scripts\git\publish_oss_to_public.bat`。

脚本会：

1. 在临时 worktree（`.git/oss-public-sync`）中从 `main` 生成 `oss-release` 分支；
2. 去掉 `docs/`、`src/proprietary/`、`src/plugins/pro/`、`src/pro_features/`；
3. 用 `--force-with-lease` 将 `oss-release` 推送到公开仓的 `main`（公开仓为开源快照，非完整历史镜像）。

**不会**切换你当前 `main` 工作区，本地闭源文件保持不动。

## 禁止操作

- **不要**执行 `git push public main`（可能把闭源推到公开仓）。
- **不要**把 `config/auth_config.json`、`config/dist_mode.json`、`.env` 提交到任一仓库。

## 查看远程配置

```powershell
git remote -v
```

预期：

- `origin` → `wemedia-baby-Pro`
- `public` → `wemedia-baby`
