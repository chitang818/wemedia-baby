"""
app_config.json 中用户偏好相关键名（与顶层业务字段如 chrome_executable_path 并存）。

维护约定：若增加新的「顶层持久化键」，请同步更新
``src.infrastructure.common.config.app_config_defaults.default_app_config_skeleton``，
以便启动时补齐缺失键、首次运行生成完整 JSON。
"""

KEY_BATCH_PUBLISH = "batch_publish"
KEY_SINGLE_PUBLISH = "single_publish"
KEY_PUBLISH_LIST = "publish_list"
KEY_UI = "ui"
KEY_PUBLISH_DIAGNOSTICS = "publish_diagnostics"

# browser / publishing safety
BROWSER_TRUST_MODE = "browser_trust_mode"
BROWSER_TRUST_MODE_REAL = "real_browser"
BROWSER_TRUST_MODE_COMPAT_STEALTH = "compat_stealth"
PUBLISH_FORCE_VISIBLE_BROWSER = "publish_force_visible_browser"
PUBLISH_RESPECT_PLATFORM_INTERVAL = "publish_respect_platform_interval"
PUBLISH_STOP_ON_RISK_PROMPT = "publish_stop_on_risk_prompt"

# publish_diagnostics
PUBLISH_DIAGNOSTICS_ENABLED = "enabled"
PUBLISH_DIAGNOSTICS_CAPTURE_HTML = "capture_html"
PUBLISH_DIAGNOSTICS_CAPTURE_DOM_SUMMARY = "capture_dom_summary"
PUBLISH_DIAGNOSTICS_MAX_HTML_BYTES = "max_html_bytes"
PUBLISH_DIAGNOSTICS_RETENTION_DAYS = "retention_days"

# batch_publish 子键
BATCH_DECLARE_ORIGINAL = "declare_original"
# 批量页「作品申明」弹窗：抖音/快手枚举（与 privacy_settings 键名一致）
BATCH_WORK_DECLARATION = "work_declaration"
BATCH_AUTO_MATCH = "auto_match"
BATCH_PUBLISH_DESCRIPTION = "publish_description"
BATCH_MEDIA_ASSIGN = "media_assign"
# 批量视频页「位置设置」弹窗（与 poi_info / 视频号空位置策略一致）
BATCH_LOCATION = "location"
BATCH_LOCATION_POI_INFO = "poi_info"
BATCH_LOCATION_WX_OPEN_PICKER = "wechat_empty_location_open_picker"

AUTO_MATCH_VIDEO_LIBRARY = "video_library"
AUTO_MATCH_IMAGE_LIBRARY = "image_library"

MEDIA_ASSIGN_STRATEGY_LIBRARY = "strategy_library"
MEDIA_ASSIGN_STRATEGY_BATCH = "strategy_batch"

# single_publish
SINGLE_DECLARE_ORIGINAL = "declare_original"
# 单视频发布页：从所选账号/账号组媒体库「视频/未发布」自动取一条素材
SINGLE_AUTO_MATCH_VIDEO_LIBRARY = "auto_match_video_library"
# 单视频发布页：按视频文件名作品编号从文案库填充标题与简介
SINGLE_AUTO_MATCH_COPYWRITING = "auto_match_copywriting"
# 单任务发布页：文案匹配模式 (standard, random_all, random_category)
SINGLE_COPYWRITING_MATCH_MODE = "copywriting_match_mode"
# 单任务发布页：随机文案匹配分类 ID
SINGLE_COPYWRITING_RANDOM_CATEGORY = "copywriting_random_category"

# publish_list
PUBLISH_LIST_DISPLAY_MODE = "display_mode"
PUBLISH_LIST_SPEED_INDEX = "speed_index"
PUBLISH_LIST_FIRST_PLATFORM = "first_platform"
PUBLISH_LIST_INTERVAL_SECONDS = "interval_seconds"
PUBLISH_LIST_POST_PUBLISH_FILE_ACTION = "post_publish_file_action"
PUBLISH_LIST_SHOW_BROWSER = "show_browser"
PUBLISH_LIST_COGNITIVE_PAUSE_ENABLED = "cognitive_pause_enabled"
PUBLISH_LIST_COGNITIVE_PAUSE_SECONDS = "cognitive_pause_seconds"
# 已废弃：发布后关机改为仅内存一次有效，不再读写此键；旧配置中若存在可忽略。
PUBLISH_LIST_AUTO_SHUTDOWN_AFTER_COMPLETE = "auto_shutdown_after_complete"

# main_window（主窗口关闭行为）
# 新版本主逻辑用顶层枚举键：main_window_close_behavior
# - remind：是否在关闭按钮时弹出“关闭/最小化到托盘”选择（旧键，兼容迁移）
# - remember_choice：是否记住上次选择（旧键，兼容迁移）
# - action：记住的动作（close | minimize_to_tray）（旧键，兼容迁移）
# main_window_close_behavior:
#   - ask：每次询问
#   - tray：最小化到托盘
#   - exit：退出应用
MAIN_WINDOW_CLOSE_BEHAVIOR = "main_window_close_behavior"
MAIN_WINDOW_CLOSE_REMIND = "main_window_close_remind"
MAIN_WINDOW_CLOSE_REMEMBER_CHOICE = "main_window_close_remember_choice"
MAIN_WINDOW_CLOSE_ACTION = "main_window_close_action"

# 关闭到托盘后，下次冷启动是否直接进入托盘（不显示主窗口）。
# 从托盘「退出」或从托盘恢复主窗口后应写入 False；默认 False 表示正常启动显示主界面。
START_IN_TRAY_NEXT_LAUNCH = "start_in_tray_next_launch"

# ui
UI_THEME_MODE = "theme_mode"
# True：缩短主窗口堆栈切换位移时间并关闭页面淡入，减轻首次进入重型页的卡顿感
UI_PAGE_ANIMATION_REDUCED = "page_animation_reduced"
# 启动后页面预加载：off | minimal | full（默认 off，低配更流畅）
UI_STARTUP_PRELOADS = "startup_preloads"
