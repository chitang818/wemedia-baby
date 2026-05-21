"""
企鹅号插件 CSS/XPath 选择器集中配置
文件路径: src/plugins/pro/qiehao/selectors.py

基于企鹅号（腾讯内容开放平台 om.qq.com）的页面 DOM 结构。
"""


class Selectors:
    # ==========================================
    # 1. 登录相关选择器 (Login)
    # ==========================================
    LOGIN = {
        "QR_CODE": [
            "img[class*='qrcode']",
            "canvas[class*='qr']",
            "div[class*='qrcode'] img",
            "div[class*='qr-code'] img",
            "img[src*='qrcode']",
            "div[class*='login-qr'] img",
        ],
        "QQ_LOGIN_BTN": [
            "a:has-text('QQ登录')",
            "div:has-text('QQ登录')",
            "button:has-text('QQ登录')",
            "a[class*='qq-login']",
            "div[class*='qq-login']",
        ],
        "WECHAT_LOGIN_BTN": [
            "a:has-text('微信登录')",
            "div:has-text('微信登录')",
            "button:has-text('微信登录')",
            "a[class*='wechat-login']",
        ],
        "LOGIN_BTN": [
            "a:has-text('登录')",
            "button:has-text('登录')",
            "div[class*='login-btn']",
        ],
    }

    USER_INFO = {
        "NICKNAME": [
            "div[class*='user-name']",
            "span[class*='user-name']",
            "div[class*='nickname']",
            "span[class*='nickname']",
            "div[class*='account-name']",
            "div[class*='header'] span[class*='name']",
            "div[class*='user-info'] span",
            "a[class*='user-name']",
        ],
        "AVATAR": [
            "img[class*='avatar']",
            "div[class*='avatar'] img",
            "div[class*='user-avatar'] img",
            "img[class*='head-img']",
        ],
    }

    REQUIRED_COOKIES = ["omtoken", "omuid", "uin"]

    # ==========================================
    # 2. 首页入口与发布导航 (Home)
    # ==========================================
    HOME = {
        "PUBLISH_BTN": [
            "a:has-text('发布视频')",
            "div:has-text('发布视频')",
            "span:has-text('发布视频')",
            "button:has-text('发布视频')",
            "a:has-text('发布')",
            "a[href*='videoPublish']",
            "a[href*='publish']",
        ],
        "UPLOAD_ENTRY": [
            "a[href*='/video/videoPublish']",
            "a[href*='videoPublish']",
            "a[href*='publish']",
            "div[class*='publish-entry']",
        ],
        "PUBLISH_PAGE_MARKER": [
            "input[type='file']",
            "div[class*='upload']",
            "div:has-text('点击上传')",
            "div:has-text('拖拽')",
            "div[class*='video-upload']",
            "div:has-text('添加视频')",
        ],
        "CREATOR_CENTER_MARKER": [
            "div:has-text('内容管理')",
            "div:has-text('数据中心')",
            "div:has-text('评论管理')",
            "a:has-text('内容管理')",
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
            "div[class*='upload-btn']",
            "div[class*='upload-trigger']",
            "div:has-text('点击上传')",
            "div:has-text('拖拽')",
            "div[class*='video-upload']",
            "button:has-text('上传')",
            "div:has-text('添加视频')",
        ],
        "UPLOAD_SUCCESS_MARKER": [
            "div[class*='video-info']",
            "div[class*='upload-success']",
            "div[class*='video-preview']",
            "video",
            "div:has-text('上传成功')",
            "div:has-text('上传完成')",
            "div[class*='progress'][style*='100']",
        ],
        "UPLOAD_PROGRESS": [
            "div[class*='progress']",
            "span[class*='progress']",
            "div[class*='percent']",
            "div[class*='upload-progress']",
        ],

        # 步骤4：标题与描述
        "TITLE_INPUT": [
            "input[placeholder*='标题']",
            "input[class*='title']",
            "div[class*='title'] input",
            "textarea[placeholder*='标题']",
            "input[maxlength='30']",
        ],
        "DESC_EDITOR": [
            "textarea[placeholder*='描述']",
            "textarea[placeholder*='简介']",
            "textarea[placeholder*='摘要']",
            "div[contenteditable='true']",
            "div[class*='desc'] textarea",
            "div[class*='description'] textarea",
            "textarea[class*='desc']",
            "div[class*='ql-editor'][contenteditable='true']",
        ],
        "TAG_INPUT": [
            "input[placeholder*='标签']",
            "input[placeholder*='话题']",
            "div[class*='tag'] input",
            "div[class*='topic'] input",
            "input[class*='tag-input']",
            "input[placeholder*='输入标签']",
        ],
        "TAG_SUGGESTION": [
            "div[class*='tag-item']",
            "li[class*='suggest-item']",
            "div[class*='topic-item']",
            "div[class*='tag-option']",
        ],

        # 步骤5：封面设置
        "COVER_BTN": [
            "div[class*='cover'] div[class*='edit']",
            "div:has-text('更改封面')",
            "button:has-text('更改封面')",
            "div:has-text('选择封面')",
            "div[class*='cover-select']",
            "div[class*='cover-btn']",
            "div[class*='cover-upload']",
            "div:has-text('上传封面')",
        ],
        "COVER_MODAL": [
            "div[class*='cover-modal']",
            "div[class*='cover-dialog']",
            "div[role='dialog']:has-text('封面')",
        ],
        "COVER_UPLOAD_BTN": [
            "div:has-text('上传封面')",
            "button:has-text('上传封面')",
            "div[class*='cover-upload']",
        ],
        "COVER_FILE_INPUT": [
            "input[type='file'][accept*='image']",
        ],
        "COVER_CONFIRM_BTN": [
            "button:has-text('完成')",
            "button:has-text('确定')",
            "button:has-text('确认')",
        ],

        # 步骤6：分类选择（企鹅号特有：内容需选择分类）
        "CATEGORY_SELECTOR": [
            "div[class*='category']",
            "select[class*='category']",
            "div[class*='classify']",
            "div:has-text('请选择分类')",
            "div[class*='type-select']",
        ],
        "CATEGORY_OPTION": [
            "li[class*='category-item']",
            "div[class*='category-option']",
            "div[class*='classify-item']",
        ],

        # 步骤7：发布按钮
        "SUBMIT_BTN": [
            "button:has-text('发布')",
            "button:has-text('立即发布')",
            "button:has-text('全部发布')",
            "button[class*='submit']",
            "button[class*='publish']",
            "div[class*='submit'] button",
            "a:has-text('发布')",
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
            "div[role='dialog']:has-text('审核')",
        ],
        "PUBLISH_TOAST_ERROR": [
            "div[class*='toast']:has-text('失败')",
            "div[class*='message']:has-text('失败')",
            "div[class*='error']",
            "div[class*='toast']:has-text('错误')",
            "div[class*='toast']:has-text('不通过')",
        ],
        "PUBLISH_TOAST_FREQ": [
            "div[class*='toast']:has-text('频繁')",
            "div[class*='message']:has-text('频繁')",
            "div:has-text('操作太频繁')",
            "div:has-text('发布上限')",
            "div:has-text('今日发布次数已用完')",
        ],
        "LOGIN_EXPIRED_INDICATORS": [
            "div:has-text('登录已过期')",
            "div:has-text('请先登录')",
            "div:has-text('请重新登录')",
            "div:has-text('登录失效')",
            "div:has-text('会话已过期')",
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
            "div:has-text('视频发布成功')",
            "div[class*='success']:has-text('成功')",
            "div:has-text('提交成功')",
        ],
        "SUCCESS_URL_KEYWORDS": [
            "/content/contentManage",
            "/article/articleManage",
            "success",
            "/manage",
        ],
        "MANAGE_PAGE_INDICATOR": [
            "div:has-text('内容管理')",
            "div:has-text('视频管理')",
            "div:has-text('我的内容')",
        ],
    }

    # ==========================================
    # 6. 发布设置 (Settings)
    # ==========================================
    SETTINGS = {
        "PUBLISH_SCHEDULE": [
            "label:has-text('定时发布')",
            "div[class*='radio']:has-text('定时发布')",
            "span:has-text('定时发布')",
            "div:has-text('定时发布')",
        ],
        "PUBLISH_NOW": [
            "label:has-text('立即发布')",
            "div[class*='radio']:has-text('立即发布')",
            "span:has-text('立即发布')",
        ],
        "SCHEDULE_INPUT": [
            "input[placeholder*='日期']",
            "input[placeholder*='时间']",
            "input[type='datetime-local']",
            "div[class*='time-picker'] input",
            "div[class*='date-picker'] input",
        ],
        "ORIGINAL_CHECKBOX": [
            "div[class*='original'] input[type='checkbox']",
            "label:has-text('原创')",
            "div:has-text('声明原创')",
            "span:has-text('声明原创')",
        ],
    }
