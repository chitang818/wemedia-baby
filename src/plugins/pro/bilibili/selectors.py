"""
哔哩哔哩插件 CSS/XPath 选择器集中配置
文件路径: src/plugins/pro/bilibili/selectors.py

所有发布步骤相关选择器均按功能分组，与标准化目录规范一致。
基于 B站创作中心 (member.bilibili.com) 的投稿页面 DOM 结构。
"""


class Selectors:
    # ==========================================
    # 1. 登录相关选择器 (Login)
    # ==========================================
    LOGIN = {
        "QR_CODE": [
            ".login-scan-box img",
            "img[class*='qrcode']",
            "canvas[class*='qr']",
            "div[class*='qrcode']",
            ".login-qrcode",
        ],
        "PHONE_INPUT": [
            "input[placeholder*='手机']",
            "input[type='tel']",
        ],
        "PASSWORD_INPUT": [
            "input[type='password']",
        ],
        "LOGIN_BTN": [
            "button:has-text('登录')",
            "button[type='submit']",
        ],
    }

    USER_INFO = {
        "NICKNAME": [
            ".header-upload-entry .nickname",
            ".mini-avatar .nickname",
            ".v-popover-content .nickname",
            "span[class*='nickname']",
            "div[class*='uname']",
            ".header-entry-mini .name",
            "a[class*='header-entry'] .name",
        ],
        "AVATAR": [
            "img[class*='avatar']",
            "div[class*='avatar'] img",
            ".header-upload-entry img",
            ".mini-avatar img",
        ],
    }

    REQUIRED_COOKIES = ["SESSDATA", "bili_jct", "DedeUserID"]

    # ==========================================
    # 2. 首页入口与发布导航 (Home)
    # ==========================================
    HOME = {
        "PUBLISH_BTN": [
            "a:has-text('投稿')",
            "a[href*='upload']",
            "div[class*='upload'] a",
            "button:has-text('投稿')",
        ],
        "UPLOAD_ENTRY": [
            "a[href*='/platform/upload/video/frame']",
            "a[href*='upload']",
        ],
        "PUBLISH_PAGE_MARKER": [
            "div[class*='upload-v2']",
            "div[class*='bcc-upload']",
            "input[type='file']",
            "div[class*='upload-btn']",
            "div[class*='video-up']",
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
            "div[class*='bcc-upload']",
            "div[class*='upload-btn']",
            "div[class*='upload-v2-container']",
            "div[class*='video-up-info']",
        ],
        "UPLOAD_SUCCESS_MARKER": [
            "div[class*='video-info-container']",
            "div[class*='file-item-inner']",
            "div[class*='upload-success']",
            "div[class*='video-info']",
        ],
        "UPLOAD_PROGRESS": [
            "div[class*='progress']",
            "span[class*='progress']",
            "div[class*='speed']",
        ],
        "REUPLOAD_BTN": [
            "div:has-text('重新上传')",
            "button:has-text('重新上传')",
            "span:has-text('重新上传')",
        ],

        # 步骤4：标题与描述
        "TITLE_INPUT": [
            "input[class*='input-val'][maxlength]",
            "input[placeholder*='标题']",
            "div[class*='title-input'] input",
            "input[class*='title']",
        ],
        "DESC_EDITOR": [
            "div[class*='ql-editor'][contenteditable='true']",
            "div[contenteditable='true'][data-placeholder*='简介']",
            "div[contenteditable='true'][data-placeholder*='描述']",
            "div[class*='desc-container'] div[contenteditable='true']",
            "div[contenteditable='true']",
        ],
        "TAG_INPUT": [
            "input[placeholder*='标签']",
            "input[placeholder*='tag']",
            "div[class*='tag-container'] input",
            "input[class*='tag-input']",
            "div[class*='label-input'] input",
        ],
        "TAG_SUGGESTION": [
            "div[class*='tag-item']",
            "li[class*='suggest-item']",
            "div[class*='topic-item']",
        ],

        # 步骤5：封面设置
        "COVER_BTN": [
            "div[class*='cover-v2'] div[class*='edit']",
            "div:has-text('更改封面')",
            "button:has-text('更改封面')",
            "div[class*='cover-select']",
            "div[class*='cover-btn']",
        ],
        "COVER_MODAL": [
            "div[class*='cover-modal']",
            "div[class*='cover-dialog']",
            "div[role='dialog']:has-text('封面')",
        ],
        "COVER_UPLOAD_BTN": [
            "div[class*='cover-upload']",
            "div:has-text('上传封面')",
            "button:has-text('上传封面')",
        ],
        "COVER_FILE_INPUT": [
            "input[type='file'][accept*='image']",
        ],
        "COVER_CONFIRM_BTN": [
            "button:has-text('完成')",
            "button:has-text('确定')",
            "button:has-text('确认')",
        ],
        "COVER_THUMB": [
            "div[class*='cover-modal'] img",
            "div[class*='cover-dialog'] img",
            "div[class*='cover-img'] img",
        ],
        "COVER_TIMELINE_ITEMS": [
            "div[class*='cover-select'] img",
            "div[class*='screenshot-item'] img",
            "div[class*='cover-list'] img",
        ],

        # 步骤7：发布按钮
        "SUBMIT_BTN": [
            "button[class*='submit-add']",
            "span:has-text('立即投稿')",
            "button:has-text('立即投稿')",
            "button:has-text('投稿')",
            "button[class*='submit']",
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
            "div[class*='verify']",
        ],
        "PUBLISH_TOAST_ERROR": [
            "div[class*='toast']:has-text('失败')",
            "div[class*='message']:has-text('失败')",
            "div[class*='error']:has-text('失败')",
        ],
        "PUBLISH_TOAST_FREQ": [
            "div[class*='toast']:has-text('频繁')",
            "div[class*='message']:has-text('频繁')",
        ],
        "LOGIN_EXPIRED_INDICATORS": [
            "div:has-text('登录已过期')",
            "div:has-text('请先登录')",
            "div:has-text('请重新登录')",
        ],
    }

    # ==========================================
    # 5. 发布结果验证 (Verify)
    # ==========================================
    VERIFY = {
        "SUCCESS_TOAST": [
            "div[class*='toast']:has-text('投稿成功')",
            "div[class*='message']:has-text('投稿成功')",
            "span:has-text('投稿成功')",
            "div:has-text('稿件投递成功')",
            "div[class*='success']:has-text('成功')",
        ],
        "SUCCESS_URL_KEYWORDS": [
            "platform/upload/video/frame/success",
            "platform/manage",
            "/success",
        ],
        "MANAGE_PAGE_INDICATOR": [
            "div:has-text('稿件管理')",
            "div:has-text('内容管理')",
        ],
    }

    # ==========================================
    # 6. 发布设置 (Settings)
    # ==========================================
    SETTINGS = {
        # 分区选择
        "TYPE_SELECTOR": [
            "div[class*='type-box']",
            "div[class*='type-item']",
            "span:has-text('请选择分区')",
            "div[class*='drop-cascader']",
        ],
        "TYPE_OPTION": [
            "li[class*='type-item']",
            "div[class*='cascader-item']",
        ],
        # 定时发布
        "PUBLISH_SCHEDULE": [
            "label:has-text('定时发布')",
            "div[class*='radio']:has-text('定时发布')",
            "input[type='radio'][value*='timing']",
        ],
        "SCHEDULE_INPUT": [
            "input[placeholder*='日期']",
            "input[placeholder*='时间']",
            "input[type='datetime-local']",
            "div[class*='time-picker'] input",
        ],
        # 原创声明
        "ORIGINAL_CHECKBOX": [
            "div[class*='original'] input[type='checkbox']",
            "label:has-text('自制')",
            "div[class*='radio']:has-text('自制')",
        ],
    }
