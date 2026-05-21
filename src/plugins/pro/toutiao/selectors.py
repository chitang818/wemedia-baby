"""
头条号插件 CSS/XPath 选择器集中配置
文件路径: src/plugins/pro/toutiao/selectors.py

所有发布步骤相关选择器均按功能分组，与标准化目录规范一致。
步骤失败时可根据报错定位到对应键名，对照文档更新 DOM 即可快速排查。

注意：头条号创作者中心 (mp.toutiao.com) DOM 结构需通过实际采集后补充精确选择器。
      当前选择器基于头条号创作者服务平台典型 DOM。
"""


class Selectors:
    # ==========================================
    # 1. 登录相关选择器 (Login)
    # ==========================================
    LOGIN = {
        "QR_CODE": [
            "img[class*='qrcode']", "canvas[class*='qr']",
            "div[class*='qrcode']", ".qrcode-image",
        ],
        "PHONE_INPUT": ["input[placeholder*='手机']", "input[type='tel']"],
        "PASSWORD_INPUT": ["input[type='password']"],
        "LOGIN_BTN": ["button:has-text('登录')", "button[type='submit']"],
    }

    USER_INFO = {
        "NICKNAME": [
            ".user-name", ".account-name",
            "span[class*='nickname']", "div[class*='nickname']",
            "span[class*='name']", ".header-user-name",
        ],
        "AVATAR": [
            "img[class*='avatar']", "div[class*='avatar'] img",
            ".user-avatar img", ".header-avatar img",
        ],
    }

    REQUIRED_COOKIES = ["sessionid", "sso_uid_tt"]

    # ==========================================
    # 2. 首页入口与发布导航 (Home)
    # ==========================================
    HOME = {
        "PUBLISH_BTN": [
            "a:has-text('发布视频')",
            "button:has-text('发布视频')",
            "a:has-text('发布作品')",
            "div[class*='publish'] button",
            "a[href*='upload']",
            "a[href*='publish']",
        ],
        "UPLOAD_ENTRY": [
            "a[href*='/xigua/upload']",
            "a[href*='/graphic/publish']",
            "a[href*='upload']",
        ],
        "PUBLISH_PAGE_MARKER": [
            "div[class*='upload']",
            "input[type='file']",
            "div[class*='publish-container']",
            "div[class*='video-publish']",
        ],
    }

    # ==========================================
    # 3. 内容发布 (Publish)
    # ==========================================
    PUBLISH = {
        # 步骤3：文件上传
        "FILE_INPUT": [
            "input[type='file']",
        ],
        "UPLOAD_BTN": [
            "div[class*='upload-wrapper']",
            "div[class*='upload-btn']",
            "div[class*='upload-area']",
            "div[class*='drag-upload']",
            "div[class*='upload']",
        ],
        "UPLOAD_SUCCESS_MARKER": [
            "div[class*='success']",
            "div[class*='preview']",
            "div[class*='video-info']",
            "div[class*='file-item']",
        ],
        "UPLOAD_PROGRESS": [
            "div[class*='progress']",
            "span[class*='progress']",
        ],
        "REUPLOAD_BTN": [
            "div:has-text('重新上传')",
            "button:has-text('重新上传')",
            "span:has-text('重新上传')",
        ],

        # 步骤4：标题与描述
        "TITLE_INPUT": [
            "input[placeholder*='标题']",
            "input[class*='title']",
            "div[class*='title'] input",
            "textarea[placeholder*='标题']",
        ],
        "DESC_EDITOR": [
            "div[contenteditable='true']",
            "textarea[placeholder*='描述']",
            "textarea[placeholder*='简介']",
            "textarea[class*='desc']",
            "div[class*='desc'] textarea",
        ],
        "TAG_INPUT": [
            "input[placeholder*='标签']",
            "input[placeholder*='话题']",
            "div[class*='tag'] input",
        ],
        "TAG_SUGGESTION": [
            "div[class*='tag-item']",
            "div[class*='suggest-item']",
            "li[class*='tag']",
        ],

        # 步骤5：封面设置
        "COVER_BTN": [
            "div:has-text('设置封面')",
            "button:has-text('设置封面')",
            "div[class*='cover'] div[class*='edit']",
            "div[class*='cover-btn']",
            "div[class*='cover-setting']",
        ],
        "COVER_MODAL": [
            "div[class*='cover-modal']",
            "div[class*='cover-dialog']",
            "div[role='dialog']:has-text('封面')",
        ],
        "COVER_UPLOAD_BTN": [
            "div[class*='cover-upload']",
            "div[class*='upload-cover']",
        ],
        "COVER_FILE_INPUT": [
            "input[type='file'][accept*='image']",
        ],
        "COVER_CONFIRM_BTN": [
            "button:has-text('确认')",
            "button:has-text('完成')",
            "button:has-text('确定')",
        ],

        # 步骤7：发布按钮
        "SUBMIT_BTN": [
            "button:has-text('发布')",
            "button:has-text('发布作品')",
            "button[class*='submit']",
            "button[class*='publish']",
        ],
    }

    # ==========================================
    # 4. 风控及异常 (Security)
    # ==========================================
    SECURITY = {
        "RISK_MODAL": [
            "div[role='dialog']:has-text('异常')",
            "div[role='dialog']:has-text('违规')",
            "div[class*='risk']",
            "div[role='dialog']:has-text('验证')",
        ],
        "PUBLISH_TOAST_ERROR": [
            "div[class*='toast']:has-text('失败')",
            "div[class*='message']:has-text('失败')",
            "div[class*='notice']:has-text('失败')",
        ],
        "PUBLISH_TOAST_FREQ": [
            "div[class*='toast']:has-text('频繁')",
            "div[class*='message']:has-text('频繁')",
        ],
        "LOGIN_EXPIRED_INDICATORS": [
            "div:has-text('登录已过期')",
            "div:has-text('请重新登录')",
        ],
    }

    # ==========================================
    # 5. 发布结果验证 (Verify)
    # ==========================================
    VERIFY = {
        "SUCCESS_TOAST": [
            "div[class*='toast']:has-text('发布成功')",
            "div[class*='message']:has-text('发布成功')",
            "span:has-text('发布成功')",
            "div[class*='toast']:has-text('提交成功')",
        ],
        "SUCCESS_URL_KEYWORDS": ["success", "manage", "content"],
        "MANAGE_PAGE_INDICATOR": [
            "div:has-text('内容管理')",
            "div:has-text('作品管理')",
        ],
    }

    # ==========================================
    # 6. 发布设置 (Settings)
    # ==========================================
    SETTINGS = {
        "PUBLISH_NOW": [
            "label:has-text('立即发布')",
            "div[class*='radio']:has-text('立即发布')",
        ],
        "PUBLISH_SCHEDULE": [
            "label:has-text('定时发布')",
            "div[class*='radio']:has-text('定时发布')",
            "input[type='checkbox'][class*='schedule']",
        ],
        "SCHEDULE_INPUT": [
            "input[placeholder*='日期']",
            "input[placeholder*='时间']",
            "input[type='datetime-local']",
        ],
        "ORIGINAL_CHECKBOX": [
            "label:has-text('声明原创')",
            "input[type='checkbox']:near(:text('原创'))",
            "div[class*='original'] input[type='checkbox']",
        ],
    }
