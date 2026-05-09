"""
多多视频插件 CSS/XPath 选择器集中配置
文件路径: src/plugins/pro/duoduoshipin/selectors.py

基于多多视频创作者中心 (live.pinduoduo.com) 的页面 DOM 结构。
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
            "div[class*='login-qrcode'] img",
            "img[src*='qrcode']",
        ],
        "REFRESH_QR_BTN": [
            "div:has-text('点击刷新')",
            "span:has-text('点击刷新')",
            "button:has-text('刷新')",
            "div[class*='qrcode-expired']",
        ],
        "LOGIN_ROLE_SWITCH": [
            "a:has-text('切换登录角色')",
            "span:has-text('切换登录角色')",
        ],
    }

    USER_INFO = {
        "NICKNAME": [
            "div[class*='user-name']",
            "span[class*='user-name']",
            "div[class*='nickname']",
            "span[class*='nickname']",
            "div[class*='username']",
            "div[class*='header'] span[class*='name']",
            "div[class*='avatar'] + span",
            "div[class*='avatar'] + div",
        ],
        "AVATAR": [
            "img[class*='avatar']",
            "div[class*='avatar'] img",
            "div[class*='user-avatar'] img",
            "img[class*='user-img']",
        ],
    }

    REQUIRED_COOKIES = ["PASS_ID", "PDDAccessToken", "pdd_user_id"]

    # ==========================================
    # 2. 首页入口与发布导航 (Home)
    # ==========================================
    HOME = {
        "PUBLISH_BTN": [
            "a:has-text('发布视频')",
            "div:has-text('发布视频')",
            "span:has-text('发布视频')",
            "button:has-text('发布视频')",
            "a[href*='short-video']",
        ],
        "UPLOAD_ENTRY": [
            "a[href*='/creator/short-video']",
            "a[href*='short-video']",
            "div[class*='upload-entry']",
        ],
        "PUBLISH_PAGE_MARKER": [
            "input[type='file']",
            "div[class*='upload']",
            "div:has-text('点击上传')",
            "div:has-text('拖拽')",
            "div[class*='video-upload']",
        ],
        "CREATOR_CENTER_MARKER": [
            "div:has-text('内容管理')",
            "div:has-text('数据中心')",
            "div:has-text('创作者中心')",
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
        ],
        "UPLOAD_SUCCESS_MARKER": [
            "div[class*='video-info']",
            "div[class*='upload-success']",
            "div[class*='video-preview']",
            "video",
            "div[class*='progress'][style*='100']",
            "div:has-text('上传成功')",
        ],
        "UPLOAD_PROGRESS": [
            "div[class*='progress']",
            "span[class*='progress']",
            "div[class*='percent']",
        ],
        "ADD_VIDEO_BTN": [
            "div:has-text('添加视频')",
            "button:has-text('添加视频')",
            "span:has-text('添加视频')",
        ],

        # 步骤4：标题与描述
        "TITLE_INPUT": [
            "input[placeholder*='标题']",
            "input[class*='title']",
            "div[class*='title'] input",
            "textarea[placeholder*='标题']",
        ],
        "DESC_EDITOR": [
            "textarea[placeholder*='描述']",
            "textarea[placeholder*='简介']",
            "div[contenteditable='true']",
            "div[class*='desc'] textarea",
            "div[class*='description'] textarea",
            "textarea[class*='desc']",
        ],
        "TAG_INPUT": [
            "input[placeholder*='标签']",
            "input[placeholder*='话题']",
            "div[class*='tag'] input",
            "div[class*='topic'] input",
            "input[class*='tag-input']",
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

        # 步骤6：商品关联（多多视频特有）
        "ADD_PRODUCT_BTN": [
            "button:has-text('添加商品')",
            "div:has-text('添加商品')",
            "span:has-text('添加商品')",
            "a:has-text('添加商品')",
        ],
        "PRODUCT_SEARCH_INPUT": [
            "input[placeholder*='商品']",
            "input[placeholder*='搜索']",
            "input[class*='product-search']",
        ],
        "PRODUCT_ITEM": [
            "div[class*='product-item']",
            "div[class*='goods-item']",
            "div[class*='commodity-item']",
        ],
        "PRODUCT_SELECT_BTN": [
            "button:has-text('选择')",
            "button:has-text('添加')",
            "span:has-text('选择')",
        ],

        # 步骤7：发布按钮
        "SUBMIT_BTN": [
            "button:has-text('发布')",
            "button:has-text('立即发布')",
            "button[class*='submit']",
            "button[class*='publish']",
            "div[class*='submit'] button",
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
            "div[class*='error']",
            "div[class*='toast']:has-text('错误')",
        ],
        "PUBLISH_TOAST_FREQ": [
            "div[class*='toast']:has-text('频繁')",
            "div[class*='message']:has-text('频繁')",
            "div:has-text('操作太频繁')",
        ],
        "LOGIN_EXPIRED_INDICATORS": [
            "div:has-text('登录已过期')",
            "div:has-text('请先登录')",
            "div:has-text('请重新登录')",
            "div:has-text('登录失效')",
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
        ],
        "SUCCESS_URL_KEYWORDS": [
            "/creator/index",
            "/creator/content",
            "success",
        ],
        "MANAGE_PAGE_INDICATOR": [
            "div:has-text('内容管理')",
            "div:has-text('视频管理')",
            "div:has-text('我的视频')",
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
        ],
        "SCHEDULE_INPUT": [
            "input[placeholder*='日期']",
            "input[placeholder*='时间']",
            "input[type='datetime-local']",
            "div[class*='time-picker'] input",
            "div[class*='date-picker'] input",
        ],
    }
