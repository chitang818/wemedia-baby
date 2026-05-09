"""
小红书插件 CSS/XPath 选择器集中配置
文件路径: src/plugins/pro/xiaohongshu/selectors.py

基于 WeMedia X-Ray DOM 分析报告 (20260306_180442) 实际采集的选择器。
已确认的选择器标注 ✅，待采集的标注 ⏳。
步骤失败时可根据报错定位到对应键名，对照文档更新 DOM 即可快速排查。
"""


class Selectors:
    # ==========================================
    # 1. 登录相关选择器 (Login)
    # ==========================================
    LOGIN = {
        "QR_CODE": [
            ".qrcode-img", "img[class*='qrcode']", "canvas[class*='qr']",
            "div[class*='qrcode']", ".login-qrcode",
        ],
        "PHONE_INPUT": ["input[placeholder*='手机']", "input[type='tel']"],
        "PASSWORD_INPUT": ["input[type='password']"],
        "LOGIN_BTN": ["button:has-text('登录')", "button[type='submit']"],
    }

    # ✅ 已确认：用户信息提取（X-Ray 20260306_180442 实采确认）
    USER_INFO = {
        # ✅ 已确认：用户头像
        # 真实 DOM: <img class="user_avatar" src="https://sns-avatar-qc.xhscdn.com/avatar/...">
        "AVATAR": [
            "img.user_avatar",
            "div[class*='avatar'] img[src*='xhscdn.com']",
            "img[src*='xhscdn.com']",
        ],
        # ✅ 已确认：用户昵称 — 位于 div.user-info 元素
        # 真实 DOM: <div class="cursor-pointer flex-center user-info">萧关郎退出登录</div>
        # 提取时需去掉 "退出登录" 后缀
        # 注意：div.name 匹配的是站点标题"创作服务平台"，不是用户名！
        "NICKNAME": [
            "div.user-info",
        ],
        # ✅ 已确认：账号信息文本区（含小红书号）
        # 真实 DOM: <div class="others description-text">小红书账号: 9402628224还没有简介</div>
        "USER_ID_TEXT": [
            "div.others.description-text",
        ],
        # ✅ 已确认：用户统计数据区
        # 真实 DOM: <div class="static description-text">14关注数193粉丝数529获赞与收藏</div>
        "USER_STATS": [
            "div.static.description-text",
        ],
    }

    # ✅ 已确认：登录成功指示器（任一命中即判定已登录）
    # 来自 X-Ray 分析报告 "关键元素匹配结果"
    LOGIN_INDICATORS = [
        "img.user_avatar",                    # 用户头像
        "div.avatar",                          # 头像容器
        "div.publish-video",                   # 发布按钮区域（仅登录后可见）
        "span.d-menu-item__title",             # 侧边栏菜单项
        "div.d-topbar-title",                  # 顶部栏（创作服务平台）
        "div.user-info",                       # 用户信息区域（含昵称）
    ]

    # ✅ 已确认：登录检测关键 Cookie（X-Ray 20260306_180442 实采确认）
    # 重要：creator.xiaohongshu.com 平台 **不使用 web_session**！
    # a1/webId/gid 是追踪 Cookie，访问登录页即设置，不是登录凭证。
    REQUIRED_COOKIES = [
        "customer-sso-sid",
        "access-token-creator.xiaohongshu.com",
        "galaxy_creator_session_id",
    ]
    CRITICAL_COOKIES = [
        "customer-sso-sid",
        "access-token-creator.xiaohongshu.com",
        "galaxy_creator_session_id",
        "galaxy.creator.beaker.session.id",
        "x-user-id-creator.xiaohongshu.com",
    ]

    # ==========================================
    # 2. 首页入口与发布导航 (Home)
    # ==========================================
    HOME = {
        # ✅ 已确认：发布笔记入口按钮
        # 真实 DOM: <div class="publish-video">
        #             <div class="btn-wrapper">
        #               <div class="btn-inner">
        #                 <svg>...</svg>
        #                 <span class="btn-text">发布笔记</span>
        #               </div>
        #             </div>
        #           </div>
        "PUBLISH_BTN": [
            "div.publish-video",
            "div.btn-wrapper",
            "span.btn-text:has-text('发布笔记')",
        ],
        # ✅ 已确认：发布图文笔记入口
        # 真实 DOM: <div class="publish-card"> 含 "发布图文笔记 支持图片格式 png、jpg、jpeg"
        "PUBLISH_IMAGE_CARD": [
            "div.publish-card:has-text('发布图文笔记')",
            "div.title:has-text('发布图文笔记')",
        ],
        # ✅ 已确认：发布视频笔记入口
        # 真实 DOM: <div class="publish-card"> 含 "发布视频笔记 支持视频格式 mp4、mov"
        "PUBLISH_VIDEO_CARD": [
            "div.publish-card:has-text('发布视频笔记')",
            "div.title:has-text('发布视频笔记')",
        ],
        # 发布页面跳转入口（直接链接）
        "UPLOAD_ENTRY": [
            "a[href*='/publish/publish']",
            "a[href*='upload']",
        ],
        # 发布页加载完成标识
        "PUBLISH_PAGE_MARKER": [
            "div[class*='upload']",
            "input[type='file']",
            "div[class*='creator-publish']",
        ],
        # ✅ 已确认：侧边栏菜单（用于页面验证）
        # 真实 DOM: <span class="d-menu-item__title"><span class="menu-title-wrapper">首页</span></span>
        "MENU_ITEMS": [
            "span.d-menu-item__title",
            "span.menu-title-wrapper",
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
            "div[class*='upload-input']",
            "div[class*='drag-over']",
            "div[class*='upload']",
        ],
        # 上传成功标识
        "UPLOAD_SUCCESS_MARKER": [
            "div[class*='success']",
            "div[class*='preview']",
            "div[class*='thumbnail']",
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
        "IMAGE_THUMBNAIL": [
            "div[class*='thumbnail'] img",
            "div[class*='preview'] img",
            "div[class*='image-item'] img",
        ],

        # 步骤4：标题与描述
        # ⏳ 标题输入框（小红书标题限 20 字，需在发布页采集精确选择器）
        "TITLE_INPUT": [
            "input[placeholder*='标题']",
            "input[class*='title']",
            "div[class*='title'] input",
        ],
        # ⏳ 描述/正文编辑器
        "DESC_EDITOR": [
            "div[contenteditable='true'][data-placeholder*='描述']",
            "div[contenteditable='true'][data-placeholder*='正文']",
            "div[contenteditable='true'][data-placeholder*='内容']",
            "div[contenteditable='true']",
        ],
        "TOPIC_INPUT": [
            "input[placeholder*='话题']",
            "input[placeholder*='标签']",
            "div[class*='topic'] input",
            "div[class*='hashtag'] input",
        ],
        "TOPIC_SUGGESTION": [
            "div[class*='topic-item']",
            "div[class*='suggest-item']",
            "li[class*='topic']",
        ],
        "AT_INPUT": ["input[placeholder*='@']"],

        # 步骤5：封面设置
        "COVER_BTN": [
            "div:has-text('设置封面')",
            "button:has-text('设置封面')",
            "div[class*='cover'] div[class*='edit']",
            "div[class*='cover-btn']",
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
        "COVER_THUMB": [
            "div[class*='cover-modal'] img",
            "div[class*='cover-dialog'] img",
        ],

        # 步骤7：发布按钮
        "SUBMIT_BTN": [
            "button:has-text('发布')",
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
        ],
        "PUBLISH_TOAST_ERROR": [
            "div[class*='toast']:has-text('失败')",
            "div[class*='message']:has-text('失败')",
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
        ],
        "SUCCESS_URL_KEYWORDS": ["publish/success", "manage", "creator"],
        "MANAGE_PAGE_INDICATOR": [
            # ✅ 已确认：侧边栏"笔记管理"
            "span.menu-title-wrapper:has-text('笔记管理')",
            "span.d-menu-item__title:has-text('笔记管理')",
            "div:has-text('内容管理')",
        ],
    }

    # ==========================================
    # 6. 发布设置 (Settings)
    # ==========================================
    SETTINGS = {
        "PRIVACY_PUBLIC": [
            "label:has-text('公开')",
            "div[class*='radio']:has-text('公开')",
        ],
        "PRIVACY_PRIVATE": [
            "label:has-text('私密')",
            "div[class*='radio']:has-text('私密')",
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
        "LOCATION_INPUT": [
            "input[placeholder*='位置']",
            "input[placeholder*='地点']",
            "div[class*='location'] input",
        ],
    }
