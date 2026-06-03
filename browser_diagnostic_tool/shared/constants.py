"""Constants shared by the standalone browser diagnostic tool."""

MODES = ("local_manual", "wmb_manual", "wmb_auto")
COLLECTORS = ("chrome_extension", "desktop_diagnostic")
STAGES = (
    "home_loaded",
    "login_observed",
    "publish_page_loaded",
    "before_upload",
    "after_upload",
    "pre_submit",
    "after_submit",
    "success_observed",
    "failure_observed",
)

SUPPORTED_PLATFORMS = ("xiaohongshu", "douyin", "wechat_video")

RISK_PROMPT_KEYWORDS = (
    "操作频繁",
    "风控",
    "异常验证",
    "安全验证",
    "验证失败",
    "环境异常",
    "风险",
    "稍后重试",
    "脚本",
    "自动化",
    "自动化软件",
    "AI",
    "人工智能",
    "验证码",
)

SENSITIVE_KEYWORDS = (
    "cookie",
    "token",
    "authorization",
    "auth",
    "secret",
    "password",
    "passwd",
    "session",
    "sid",
)

