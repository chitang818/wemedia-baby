# WeMediaBaby 项目说明

本文档记录当前项目的结构、运行方式和开发约定，供后续 AI agent 或开发者快速接手。

## 项目定位

WeMediaBaby（媒小宝）是一个面向自媒体运营的 Windows 桌面端自动发布工具。核心能力是管理多个平台账号、创建发布任务、维护素材/文案，并通过浏览器自动化把视频或图文发布到创作者平台。

当前开源主线以 Community/OSS 能力为主，Pro/闭源能力通过功能开关、可选模块和可选插件接入。代码里已经保留了批量发布、素材库、带货推广、数据中心、互动管理、订阅权限等 Pro 功能的入口和降级逻辑。

## 技术栈

- 语言：Python 3.10+，项目建议 Python 3.12。
- 桌面 UI：PySide6、PySide6-Fluent-Widgets。
- 异步集成：qasync，将 asyncio 与 Qt 事件循环结合。
- 浏览器自动化：Playwright、undetected-playwright。
- 数据库：SQLite，异步访问以 Tortoise ORM / aiosqlite 为主。
- 配置与数据模型：Pydantic、JSON 配置文件。
- 测试：pytest、pytest-asyncio、pytest-cov、pytest-html、pytest-mock、Hypothesis。
- 打包：PyInstaller、Nuitka，Inno Setup 用于 Windows 安装包脚本。

## 关键入口

- `main.py`：应用统一启动入口。负责设置路径、Qt/Chromium 环境变量、全局异常钩子、Windows SEH 崩溃日志、qfluentwidgets 退出噪声过滤等启动前置逻辑。
- `src/ui/main_window.py`：主窗口实现，基于 `FluentWindow`。负责导航、状态栏、托盘、事件订阅、页面预加载和页面切换。
- `src/ui/page_factory.py`：页面工厂。按页面名懒加载 UI 页面，避免启动时导入所有重型页面。
- `src/ui/navigation_config.py`：导航菜单配置。根据 feature flag 动态注入 OSS/Pro 页面入口。
- `config/feature_flags.py`：发行模式和功能开关。`APP_DIST_MODE` 或 `config/dist_mode.json` 可决定 `OSS`、`PRO`、`52POJIE` 模式。

## 目录结构

- `config/`：平台配置、选择器配置、UI 配置、功能开关、认证配置示例。
- `resources/`：应用图标、平台图标、截图和静态资源。
- `scripts/`：测试、发布、维护、清理、版本升级等脚本。
- `installers/`：Windows 安装包相关脚本，目前包含 Inno Setup 配置。
- `src/domain/`：领域模型、仓储接口和发布领域规则。
- `src/services/`：应用服务层，包含账号、认证、浏览器、发布、素材、订阅、工作台等业务服务。
- `src/infrastructure/`：基础设施层，包含浏览器管理、存储、缓存、网络、监控、配置中心、事件总线、依赖注入、安全等。
- `src/plugins/`：平台插件体系。`community/` 中有开源平台插件，`core/` 中有插件接口与管理器。
- `src/ui/`：PySide6 表现层，包含页面、组件、对话框、样式、ViewModel、工具函数。
- `src/utils/`：跨层通用工具。
- `tests/`：测试目录，分为 `unit/`、`integration/`、`smoke/` 和 `helpers/`。

## 主要业务模块

### 账号与浏览器

账号相关逻辑集中在：

- `src/services/account/`
- `src/ui/pages/account/`
- `src/domain/repositories/account_*`
- `src/infrastructure/browser/`
- `src/services/browser/playwright_service.py`

账号浏览器数据目录通过 `PathManager` 统一生成。平台账号目录只允许使用 `profile_folder_name` 作为 `data/{platform}/{profile_xxx}` 下的目录名，不应使用平台昵称建目录。

### 发布流水线

发布主流程采用 pipeline/filter 结构：

- `src/services/publish/pipeline/pipeline_factory_async.py`
- `src/infrastructure/common/pipeline/publish_pipeline.py`
- `src/services/publish/pipeline/filters/`
- `src/infrastructure/common/pipeline/filters/execution_filter.py`

异步发布流水线目前按顺序注册：

1. 权限检查 `PermissionCheckFilterAsync`
2. 媒体验证 `MediaValidateFilterAsync`
3. 账号加载 `AccountLoadFilterAsync`
4. 平台插件执行 `PublishExecutionFilter`
5. 发布记录保存 `RecordSaveFilterAsync`

流水线默认 `max_concurrent=3`。发布动作最终通过平台发布插件执行。

### 插件体系

插件接口位于：

- `src/plugins/core/interfaces/login_plugin.py`
- `src/plugins/core/interfaces/publish_plugin.py`
- `src/plugins/core/plugin_manager.py`

登录插件需要提供平台标识、平台名、登录 URL、登录状态检测、账号信息提取和 Cookie/账号状态验证能力。发布插件需要提供表单 schema 和异步 `publish(context, file_path, metadata)` 方法，返回 `PublishResult`。

`PluginManager` 默认按需加载插件。设置 `PLUGIN_EAGER_INIT=1` 时会启动期全量导入，主要用于兼容旧行为或排查打包收集问题。

已注册的平台 ID 包括：

- 社区插件：`douyin`、`kuaishou`
- Pro/可选插件：`wechat_video`、`xiaohongshu`、`bilibili`、`weibo`、`toutiao`、`baijiahao`、`duoduoshipin`、`qiehao`

注意：注册表中包含 Pro 模块路径，但开源环境下这些模块可能不存在。相关导入失败应被视为正常降级场景。

### 数据与存储

路径统一由 `src/infrastructure/common/path_manager.py` 管理：

- 开发环境资源根目录：项目根目录。
- 打包环境资源根目录：PyInstaller `_MEIPASS` 或可执行文件所在目录。
- 用户数据目录：Windows 下为 `%LOCALAPPDATA%\WeMediaBaby`。
- 默认数据库：`%LOCALAPPDATA%\WeMediaBaby\data\database.db`。
- 日志目录：`%LOCALAPPDATA%\WeMediaBaby\logs`。
- 调试截图：`%LOCALAPPDATA%\WeMediaBaby\debug\screenshots`。

Tortoise ORM 生命周期在 `src/infrastructure/storage/tortoise_manager.py`。初始化时会：

- 创建 SQLite 数据库目录。
- 初始化 Tortoise ORM。
- 设置 WAL、busy timeout、cache 等 SQLite PRAGMA。
- `generate_schemas(safe=True)` 自动建表。
- 对部分旧表执行轻量列迁移和索引补全。

ORM 模型位于 `src/infrastructure/storage/orm_models/`，包括用户、订阅、平台账号、登录日志、发布记录、批量任务、素材文案、带货商品等。

## 配置文件

- `pyproject.toml`：项目元数据、核心依赖、Pyright 配置。
- `requirements.txt`：通过 `-c constraints.txt` 约束后安装当前项目。
- `requirements-dev.txt`：开发和测试依赖。
- `requirements-build.txt`：打包依赖。
- `constraints.txt`：锁定依赖版本，用于可复现安装。
- `pytest.ini`：pytest 路径、marker、异步模式、临时目录和默认参数。
- `version.json`：当前版本与更新信息。当前版本为 `1.3.9`，发布日期为 `2026-05-27`。
- `config/platforms/*.json`：平台基础配置，包含 URL、支持格式、大小限制、超时、发布间隔、选择器文件、反风控参数等。
- `config/selectors/*.json`：平台页面选择器配置。

## 常用命令

安装运行依赖：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

安装开发测试依赖：

```powershell
pip install -r requirements-dev.txt
```

以 OSS 模式启动：

```powershell
$env:APP_DIST_MODE="OSS"
python main.py
```

运行完整测试：

```powershell
python scripts/test/run_tests.py
```

只运行单元测试：

```powershell
python scripts/test/run_tests.py unit
```

快速测试，跳过 slow：

```powershell
python scripts/test/run_tests.py --quick
```

按关键字筛选测试：

```powershell
python scripts/test/run_tests.py --module keyword
```

不生成覆盖率报告：

```powershell
python scripts/test/run_tests.py unit --no-cov
```

直接使用 pytest：

```powershell
python -m pytest tests/unit
```

## 测试约定

- 测试文件命名为 `test_*.py`。
- pytest marker：
  - `unit`：单元测试。
  - `integration`：集成测试，可能依赖数据库或文件系统。
  - `slow`：慢测试，`--quick` 会跳过。
- `scripts/test/run_tests.py` 会先执行 UTF-8 文本编码检查，除非传入 `--skip-encoding-check`。
- 测试报告输出到 `test-reports/`，覆盖率 HTML 输出到 `test-reports/coverage/`。
- pytest 临时目录默认使用 `.pytest-tmp`。

## 开发注意事项

- 项目含大量中文文案和注释，新增或修改文本文件时应使用 UTF-8 编码。
- 不要绕过 `PathManager` 手写资源、数据库、日志、账号数据路径，尤其要兼容打包环境。
- UI 页面应通过 `PageFactory` 注册和懒加载，避免主窗口启动时导入重型模块。
- 新增导航入口时同步更新 `NavigationConfig`、`PageFactory` 和必要的 feature flag。
- 新增平台时优先实现 `LoginPluginInterface` 和 `PublishPluginInterface`，再在 `PluginManager.PLUGIN_REGISTRY` 和 `config/platforms/` 中注册。
- Pro/可选模块缺失是允许的，不应让 OSS 启动失败。
- Qt 控件只能在 UI 线程操作；异步任务与 UI 交互应使用已有的 qasync/Qt 线程切换工具。
- 发布流程改动要关注流水线 filter 顺序、事件总线通知、发布记录落库和失败截图/日志。
- 数据库结构变更要考虑旧库兼容。当前项目存在启动期轻量迁移逻辑，必要时补充测试。
- 浏览器自动化相关代码需要兼顾登录态持久化、Cookie 加密/保存、反风控延迟和失败诊断。
- 不要提交本地生成物、缓存、测试报告、打包产物或用户数据。

## Git 双仓库（私有主仓）

- **主远程 `origin`**：`wemedia-baby-Pro`（私有），`main` 含开源 + 闭源；日常 `git push origin main`。
- **公开远程 `public`**：`wemedia-baby`（开源）；仅通过 `scripts/git/publish_oss_to_public.ps1`（或 `.bat`）同步，**禁止** `git push public main`。
- 建议执行一次 `scripts/git/install_git_hooks.ps1` 安装 pre-push 防误推钩子。
- 详细流程见 [docs/internal/GIT_DUAL_REPO.md](docs/internal/GIT_DUAL_REPO.md)。

## 当前工作区状态提示

后续开发前先执行 `git status --short`，避免误改或回滚他人工作。
