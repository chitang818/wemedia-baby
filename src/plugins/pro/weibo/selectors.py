"""
新浪微博插件 CSS/XPath 选择器集中配置
文件路径: src/plugins/pro/weibo/selectors.py

所有发布步骤相关选择器均按功能分组，与标准化目录规范一致。
基于微博创作者中心 (weibo.com) 的视频发布页面 DOM 结构。

说明：
  微博网页版视频发布页面位于 weibo.com/upload/channel，
  用户需先登录后进入该页面进行视频上传和发布。
  选择器基于微博当前（2026年）的 DOM 结构编写，若微博改版需更新。
"""


class Selectors:
    # ==========================================
    # 1. 登录相关选择器 (Login)
    # ==========================================
    LOGIN = {
        "QR_CODE": [
            "img[class*='qrcode']",
            "div[class*='qrcode'] img",
            "div[class*='QR'] img",
            "img[node-type='qrcode_image']",
            "canvas[class*='qr']",
        ],
        "PHONE_INPUT": [
            "input[name='username']",
            "input[placeholder*='手机']",
            "input[placeholder*='邮箱']",
            "input[id='loginname']",
            "input[type='text'][name*='user']",
        ],
        "PASSWORD_INPUT": [
            "input[name='password']",
            "input[type='password']",
        ],
        "LOGIN_BTN": [
            "button:has-text('登录')",
            "a:has-text('登录')",
            "input[type='submit']",
            "button[node-type='submitBtn']",
        ],
    }

    USER_INFO = {
        "NICKNAME": [
            "a[class*='name'] span",
            "span[class*='screen_name']",
            "a[class*='ALink_none'] span",
            "div[class*='woo-box-flex'] a span",
            "a[href*='/profile'] span",
            "span[class*='userName']",
            "div[class*='Nav_user'] span",
        ],
        "AVATAR": [
            "img[class*='avatar']",
            "img[class*='head']",
            "div[class*='avatar'] img",
            "a[class*='head'] img",
        ],
    }

    REQUIRED_COOKIES = ["SUB", "SUBP"]

    # ==========================================
    # 2. 首页入口与发布导航 (Home)
    # ==========================================
    HOME = {
        "PUBLISH_BTN": [
            "a:has-text('发视频')",
            "button:has-text('发布')",
            "div:has-text('发布视频')",
            "a[href*='upload']",
            "div[class*='publish'] a",
        ],
        "UPLOAD_ENTRY": [
            "a[href*='/upload/channel']",
            "a[href*='upload']",
            "div[class*='woo-box'] a[href*='upload']",
        ],
        "PUBLISH_PAGE_MARKER": [
            "input[type='file']",
            "div[class*='upload']",
            "div[class*='Upload']",
            "div[class*='video-upload']",
            "div[class*='woo-upload']",
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
            "div[class*='Upload']",
            "div[class*='woo-upload']",
            "div[class*='video-upload']",
            "div:has-text('点击上传')",
            "div:has-text('拖拽上传')",
        ],
        "UPLOAD_SUCCESS_MARKER": [
            "div[class*='video-info']",
            "div[class*='progress'][style*='100']",
            "div[class*='upload-success']",
            "div:has-text('上传成功')",
            "div:has-text('上传完成')",
            "div[class*='VideoInfo']",
        ],
        "UPLOAD_PROGRESS": [
            "div[class*='progress']",
            "span[class*='progress']",
            "div[class*='percent']",
        ],
        "REUPLOAD_BTN": [
            "div:has-text('重新上传')",
            "button:has-text('重新上传')",
            "a:has-text('重新上传')",
        ],

        # 步骤4：标题与描述
        "TITLE_INPUT": [
            "input[placeholder*='标题']",
            "input[placeholder*='视频标题']",
            "input[class*='title']",
            "div[class*='title'] input",
            "input[maxlength]",
        ],
        "DESC_EDITOR": [
            "textarea[placeholder*='简介']",
            "textarea[placeholder*='描述']",
            "textarea[placeholder*='说点什么']",
            "textarea[placeholder*='视频简介']",
            "div[contenteditable='true']",
            "textarea[class*='desc']",
            "textarea[class*='content']",
            "div[class*='ql-editor'][contenteditable='true']",
        ],
        "TAG_INPUT": [
            "input[placeholder*='话题']",
            "input[placeholder*='标签']",
            "input[placeholder*='添加话题']",
            "div[class*='topic'] input",
            "div[class*='tag'] input",
        ],
        "TAG_SUGGESTION": [
            "div[class*='topic-item']",
            "li[class*='suggest-item']",
            "div[class*='tag-item']",
        ],

        # 步骤5：封面设置
        "COVER_BTN": [
            "div:has-text('更换封面')",
            "div:has-text('选择封面')",
            "button:has-text('更换封面')",
            "div[class*='cover'] div[class*='edit']",
            "div[class*='cover-btn']",
            "div[class*='Cover'] button",
        ],
        "COVER_MODAL": [
            "div[class*='cover-modal']",
            "div[class*='cover-dialog']",
            "div[role='dialog']:has-text('封面')",
            "div[class*='Modal']:has-text('封面')",
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
            "div[class*='screenshot'] img",
            "div[class*='cover-list'] img",
        ],

        # 步骤7：发布按钮
        "SUBMIT_BTN": [
            "button:has-text('发布')",
            "button:has-text('立即发布')",
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
            "div[role='dialog']:has-text('验证')",
            "div[class*='verify']",
            "div[class*='risk']",
            "div[class*='captcha']",
        ],
        "PUBLISH_TOAST_ERROR": [
            "div[class*='toast']:has-text('失败')",
            "div[class*='message']:has-text('失败')",
            "div[class*='woo-toast']:has-text('失败')",
            "div[class*='error']",
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
            "div:has-text('未登录')",
        ],
    }

    # ==========================================
    # 5. 发布结果验证 (Verify)
    # ==========================================
    VERIFY = {
        "SUCCESS_TOAST": [
            "div:has-text('发布成功')",
            "div[class*='toast']:has-text('成功')",
            "div[class*='woo-toast']:has-text('成功')",
            "span:has-text('发布成功')",
            "div[class*='success']",
        ],
        "SUCCESS_URL_KEYWORDS": [
            "/tv/show/",
            "video.weibo.com",
            "/detail/",
            "weibo.com/u/",
        ],
        "MANAGE_PAGE_INDICATOR": [
            "div:has-text('作品管理')",
            "div:has-text('视频管理')",
            "div:has-text('内容管理')",
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
            "div:has-text('定时发布') input[type='radio']",
        ],
        "SCHEDULE_INPUT": [
            "input[placeholder*='日期']",
            "input[placeholder*='时间']",
            "input[type='datetime-local']",
            "div[class*='time-picker'] input",
            "div[class*='date-picker'] input",
        ],
        "CATEGORY_SELECTOR": [
            "div[class*='category']",
            "div:has-text('选择分类')",
            "select[class*='category']",
            "div[class*='type-select']",
        ],
        "CATEGORY_OPTION": [
            "li[class*='category-item']",
            "div[class*='option']",
        ],
        "ORIGINAL_CHECKBOX": [
            "label:has-text('原创')",
            "div[class*='checkbox']:has-text('原创')",
            "input[type='checkbox'][name*='original']",
        ],
    }
