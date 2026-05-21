"""
百家号插件 CSS/XPath 选择器集中配置
文件路径: src/plugins/pro/baijiahao/selectors.py

所有发布步骤相关选择器均按功能分组，与标准化目录规范一致。
基于百家号创作中心 (baijiahao.baidu.com) 的发布页面 DOM 结构。

注意：百家号创作中心使用 cheetah-* 命名的组件体系，
      DOM 结构可能随版本升级变化，需定期通过 X-Ray 工具核实。
"""


class Selectors:
    # ==========================================
    # 1. 登录相关选择器 (Login)
    # ==========================================
    LOGIN = {
        "QR_CODE": [
            "div[class*='qrcode'] img",
            "img[class*='qrcode']",
            "canvas[class*='qr']",
            "div[class*='qr-img']",
            "#login-qrcode img",
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
            "input[type='submit']",
            "button[type='submit']",
        ],
    }

    USER_INFO = {
        "NICKNAME": [
            ".app-header-username",
            ".user-name",
            ".header-user-name",
            "span[class*='username']",
            "span[class*='user-name']",
            "div[class*='user-info'] span",
            ".cheetah-header .user-name",
        ],
        "AVATAR": [
            "img[class*='avatar']",
            "div[class*='avatar'] img",
            ".header-avatar img",
            ".app-header-avatar img",
        ],
    }

    REQUIRED_COOKIES = ["BDUSS", "STOKEN"]

    # ==========================================
    # 2. 首页入口与发布导航 (Home)
    # ==========================================
    HOME = {
        "PUBLISH_BTN": [
            "a:has-text('发布')",
            "button:has-text('发布')",
            "a[href*='edit']",
            "div[class*='publish'] a",
            ".aside-publish-btn",
        ],
        "VIDEO_PUBLISH_ENTRY": [
            "a:has-text('发布视频')",
            "a[href*='edit?type=video']",
            "div[class*='video'] a",
            "li:has-text('发布视频') a",
        ],
        "UPLOAD_ENTRY": [
            "a[href*='/builder/rc/edit']",
            "a[href*='upload']",
        ],
        "PUBLISH_PAGE_MARKER": [
            "div[class*='editor-container']",
            "div[class*='video-upload']",
            "div[class*='bjh-editor']",
            "input[type='file']",
            "div[class*='upload-area']",
            "div[class*='cheetah-editor']",
        ],
    }

    # ==========================================
    # 3. 内容发布 (Publish)
    # ==========================================
    PUBLISH = {
        # 步骤3：文件上传
        "FILE_INPUT": [
            "input[type='file']",
            "input[type='file'][accept*='video']",
        ],
        "UPLOAD_BTN": [
            "div[class*='upload-area']",
            "div[class*='video-upload']",
            "div[class*='upload-btn']",
            "div[class*='drag-upload']",
            "div[class*='upload-wrapper']",
        ],
        "UPLOAD_SUCCESS_MARKER": [
            "div[class*='video-info']",
            "div[class*='upload-success']",
            "div[class*='file-item']",
            "div[class*='video-card']",
            "div[class*='upload-complete']",
        ],
        "UPLOAD_PROGRESS": [
            "div[class*='progress']",
            "span[class*='progress']",
            "div[class*='upload-progress']",
        ],
        "REUPLOAD_BTN": [
            "span:has-text('重新上传')",
            "button:has-text('重新上传')",
            "a:has-text('重新上传')",
            "div:has-text('重新上传')",
        ],

        # 步骤4：标题与描述
        "TITLE_INPUT": [
            "input[placeholder*='标题']",
            "input[class*='title-input']",
            "div[class*='title'] input",
            "textarea[placeholder*='标题']",
            "input[maxlength='30']",
        ],
        "DESC_EDITOR": [
            "div[contenteditable='true']",
            "div[class*='ql-editor'][contenteditable='true']",
            "div[class*='desc-editor'] div[contenteditable='true']",
            "textarea[placeholder*='简介']",
            "textarea[placeholder*='描述']",
            "div[class*='video-desc'] textarea",
        ],
        "TAG_INPUT": [
            "input[placeholder*='标签']",
            "input[placeholder*='话题']",
            "div[class*='tag-input'] input",
            "div[class*='label-input'] input",
            "input[class*='tag']",
        ],
        "TAG_SUGGESTION": [
            "div[class*='tag-item']",
            "li[class*='suggest-item']",
            "div[class*='topic-item']",
            "div[class*='tag-suggest']",
        ],

        # 步骤5：封面设置
        "COVER_BTN": [
            "div[class*='cover'] div[class*='edit']",
            "div:has-text('更改封面')",
            "button:has-text('更改封面')",
            "div[class*='cover-btn']",
            "div[class*='cover-edit']",
            "span:has-text('设置封面')",
        ],
        "COVER_MODAL": [
            "div[class*='cover-modal']",
            "div[class*='cover-dialog']",
            "div[role='dialog']:has-text('封面')",
            "div[class*='modal']:has-text('封面')",
        ],
        "COVER_UPLOAD_BTN": [
            "div[class*='cover-upload']",
            "div:has-text('上传封面')",
            "button:has-text('上传封面')",
            "span:has-text('上传封面')",
        ],
        "COVER_FILE_INPUT": [
            "input[type='file'][accept*='image']",
        ],
        "COVER_CONFIRM_BTN": [
            "button:has-text('确定')",
            "button:has-text('确认')",
            "button:has-text('完成')",
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
            "button:has-text('发布')",
            "button[class*='publish']",
            "button[class*='submit']",
            "span:has-text('发布'):not([class*='schedule'])",
            "div[class*='publish-btn'] button",
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
            "div[class*='captcha']",
        ],
        "PUBLISH_TOAST_ERROR": [
            "div[class*='toast']:has-text('失败')",
            "div[class*='message']:has-text('失败')",
            "div[class*='error']:has-text('失败')",
            "div[class*='notification']:has-text('失败')",
        ],
        "PUBLISH_TOAST_FREQ": [
            "div[class*='toast']:has-text('频繁')",
            "div[class*='message']:has-text('频繁')",
        ],
        "LOGIN_EXPIRED_INDICATORS": [
            "div:has-text('登录已过期')",
            "div:has-text('请先登录')",
            "div:has-text('请重新登录')",
            "div:has-text('登录状态已失效')",
        ],
        "POPUP_CLOSE_BTN": [
            "div[class*='modal'] button[class*='close']",
            "div[class*='dialog'] button[class*='close']",
            "i[class*='close']",
            "span[class*='close']",
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
            "div:has-text('发布成功')",
            "div[class*='success']:has-text('成功')",
        ],
        "SUCCESS_URL_KEYWORDS": [
            "/builder/rc/home",
            "publish/success",
            "/builder/rc/content",
        ],
        "MANAGE_PAGE_INDICATOR": [
            "div:has-text('内容管理')",
            "div:has-text('作品管理')",
            "div:has-text('视频管理')",
        ],
    }

    # ==========================================
    # 6. 发布设置 (Settings)
    # ==========================================
    SETTINGS = {
        # 定时发布
        "PUBLISH_SCHEDULE": [
            "label:has-text('定时发布')",
            "div[class*='radio']:has-text('定时发布')",
            "span:has-text('定时发布')",
            "input[type='radio'][value*='timing']",
        ],
        "SCHEDULE_INPUT": [
            "input[placeholder*='日期']",
            "input[placeholder*='时间']",
            "input[type='datetime-local']",
            "div[class*='time-picker'] input",
            "div[class*='date-picker'] input",
        ],
        # 原创声明
        "ORIGINAL_CHECKBOX": [
            "label:has-text('原创')",
            "div[class*='original'] input[type='checkbox']",
            "span:has-text('声明原创')",
            "input[type='checkbox']:near(:text('原创'))",
        ],
        # 分类选择
        "CATEGORY_SELECTOR": [
            "div[class*='category']",
            "select[class*='category']",
            "div[class*='type-select']",
            "span:has-text('请选择分类')",
        ],
        "CATEGORY_OPTION": [
            "li[class*='category-item']",
            "div[class*='cascader-item']",
            "div[class*='option']",
        ],
    }
