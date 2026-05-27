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
            "xpath=//*[normalize-space()='发布图文笔记']/ancestor::*[contains(@class,'publish-card')][1]",
            "div.publish-card:has-text('发布图文笔记')",
            "div[class*='publish-card']:has-text('发布图文笔记')",
            "[class*='publish']:has-text('发布图文笔记')",
            "text=发布图文笔记",
            "div.title:has-text('发布图文笔记')",
        ],
        # ✅ 已确认：发布视频笔记入口
        # 真实 DOM: <div class="publish-card"> 含 "发布视频笔记 支持视频格式 mp4、mov"
        "PUBLISH_VIDEO_CARD": [
            "xpath=//*[normalize-space()='发布视频笔记']/ancestor::*[contains(@class,'publish-card')][1]",
            "div.publish-card:has-text('发布视频笔记')",
            "div[class*='publish-card']:has-text('发布视频笔记')",
            "[class*='publish']:has-text('发布视频笔记')",
            "text=发布视频笔记",
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
        # 上传成功标识（保留给图文/历史兜底使用；视频完成态不要依赖这些宽泛 class）
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
        # 发布页 SPA 骨架屏（加载中灰色占位块）；步骤3 需在其消退后再操作/判定完成
        "PUBLISH_FORM_LOADING": [
            "[class*='skeleton']",
            ".el-skeleton",
            ".el-skeleton__item",
            "[class*='Skeleton']",
        ],
        # 发布表单就绪：上传区文案已渲染（区别于仅存在 input[type=file]）
        "PUBLISH_FORM_READY": [
            "xpath=//*[normalize-space()='视频文件']",
            "text=视频文件",
            ".creator-tab.active:has-text('上传视频')",
            "div:has-text('上传视频'):has-text('视频格式')",
        ],
        # 视频上传成功判定：视频文件卡片右上角出现「重新上传」按钮即表示上传完成。
        # 优先用「视频文件」区域约束，避免 preview/thumbnail/file-item 提前出现造成误判。
        "VIDEO_UPLOAD_SUCCESS_MARKER": [
            "xpath=//*[normalize-space()='视频文件']/ancestor::*[contains(@class,'card') or contains(@class,'upload') or contains(@class,'video') or contains(@class,'section') or contains(@class,'container')][1]//*[normalize-space()='重新上传']",
            "xpath=//*[normalize-space()='视频文件']/ancestor::*[self::div or self::section][1]//*[normalize-space()='重新上传']",
            "div:has-text('视频文件') button:has-text('重新上传')",
            "div:has-text('视频文件') span:has-text('重新上传')",
            "div:has-text('视频文件') :has-text('重新上传')",
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

        # ---- 图文发布专用选择器 ----
        # 图文 input[type=file]：优先限定 accept=image/* 避免误取视频 input
        "IMAGE_FILE_INPUT": [
            "input[type='file'][accept*='image']",
            "input[type='file'][accept*='png']",
            "input[type='file'][accept*='jpg']",
            "input[type='file']:not([accept*='video'])",
            "input[type='file']",
        ],
        # 图文发布页上传触发按钮 / 拖拽区域
        "IMAGE_UPLOAD_BTN": [
            "div[class*='upload-wrapper']",
            "div[class*='upload-input']",
            "div[class*='drag-over']",
            "div[class*='upload']",
            "button:has-text('上传图片')",
            "div:has-text('点击上传')",
        ],
        # 图文上传完成标志：出现预览图即视为上传就绪
        # 小红书图文页以缩略图或图片计数作为就绪信号
        "IMAGE_UPLOAD_SUCCESS": [
            "div[class*='image-item'] img",
            "div[class*='thumbnail'] img",
            "div[class*='preview'] img",
            "div[class*='upload-list'] img",
            "div[class*='file-list'] img",
            "img[class*='preview']",
        ],

        # 步骤5：标题与描述
        # ⏳ 标题输入框（小红书标题限 20 字，需在发布页采集精确选择器）
        "TITLE_INPUT": [
            "input[placeholder*='标题']",
            "input[class*='title']",
            "div[class*='title'] input",
        ],
        # 描述/正文编辑器（优先带 placeholder 的发布描述区）
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
        # 描述区工具条「# 话题」（勿用宽泛 button:has-text('话题')，易误点侧栏）
        "TOPIC_ENTRY_BTN": [
            "span:has-text('# 话题')",
            "div:has-text('# 话题')",
            "button:has-text('# 话题')",
            "[class*='toolbar'] :text('# 话题')",
            "[class*='editor'] :text('# 话题')",
        ],
        "TOPIC_DROPDOWN": [
            "[role='listbox']",
            "div[class*='dropdown']",
            "div[class*='popover']",
            "div[class*='suggest']",
            "div[class*='mention']",
            "div[class*='selector']",
        ],
        "TOPIC_SUGGESTION": [
            "[role='listbox'] [role='option']",
            "[role='listbox'] li",
            "div[class*='topic-item']",
            "div[class*='suggest-item']",
            "li[class*='topic']",
            "div[class*='dropdown'] div[class*='item']",
        ],
        # 已收成的话题芯片（用于计数后验）
        "TOPIC_CHIP": [
            "a[class*='tag']",
            "span[class*='tag']",
            "[class*='topic-tag']",
            "[class*='hashtag']",
            "[class*='topic-item']",
            "a[data-topic]",
        ],
        "AT_INPUT": ["input[placeholder*='@']"],

        # 步骤4：封面设置
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

        # 步骤8：xhs-publish-btn（closed Shadow）内 button.ce-btn.bg-red
        # 立即：submit-text=发布；定时：submit-text=定时发布；须排除 Shadow 内「暂存离开」
        # 勿用全局 :has-text('定时发布')，会命中更多设置开关
        "SUBMIT_BTN_SHADOW": [
            ".publish-page-content xhs-publish-btn >> button.ce-btn.bg-red",
            ".publish-page-container xhs-publish-btn >> button.ce-btn.bg-red",
            "#publish-container xhs-publish-btn >> button.ce-btn.bg-red",
            "xhs-publish-btn >> button.ce-btn.bg-red",
        ],
        "SUBMIT_BTN": [
            ".publish-page-content xhs-publish-btn[is-publish='true']",
            ".publish-page-container xhs-publish-btn[is-publish='true']",
            "#publish-container xhs-publish-btn[is-publish='true']",
            "xhs-publish-btn[is-publish='true']",
            ".publish-page-content button:has-text('发布')",
            ".publish-page-container button:has-text('发布')",
            ".publish-page-footer button:has-text('发布')",
            "#publish-container button:has-text('发布')",
            # 勿用全局 button:has-text('定时发布')，会命中「更多设置」开关而非底部提交钮
            "button[class*='submit']",
            "button[class*='publish']",
        ],
        "SUBMIT_SCOPE": [
            ".publish-page-content",
            ".publish-page-container",
            "#publish-container",
            ".publish-page-footer",
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
            "div[class*='toast']:has-text('定时发布成功')",
            "div[class*='message']:has-text('定时发布')",
            "span:has-text('定时发布成功')",
        ],
        "SUCCESS_URL_KEYWORDS": [
            "published=true",
            "publish/success",
            "manage",
            "creator",
        ],
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
        # 步骤7：更多设置区（20260525 DOM 报告）
        "MORE_SETTINGS_SECTION": [
            ".publish-page-content-settings",
        ],
        "PERMISSION_SELECT": [
            ".publish-page-content-settings .permission-card-select",
            ".permission-card-select",
        ],
        "PERMISSION_DROPDOWN": [
            "body > .d-popover.custom-dropdown-44:has-text('仅自己可见')",
            "body > .d-popover.d-dropdown.custom-dropdown-44:has-text('仅自己可见')",
        ],
        "PERMISSION_DROPDOWN_ANCHOR": [
            "仅自己可见",
        ],
        "SCHEDULE_WRAPPER": [
            ".publish-page-content-settings .post-time-wrapper",
            ".post-time-wrapper",
        ],
        "SCHEDULE_LABEL": [
            "text=定时发布",
        ],
        "SCHEDULE_CHECKBOX": [
            ".publish-page-content-settings .post-time-wrapper input[type='checkbox']",
            ".post-time-wrapper input[type='checkbox']",
        ],
        "SCHEDULE_SWITCH": [
            ".post-time-switch-container .d-switch-simulator",
            ".post-time-switch-container .d-clickable.d-switch",
            ".post-time-wrapper .d-switch-simulator",
            ".post-time-wrapper .d-clickable.d-switch",
            ".post-time-wrapper .custom-switch-card",
            ".post-time-wrapper .custom-switch-wrapper",
        ],
        "SCHEDULE_TIME_INPUT": [
            ".post-time-wrapper input[type='text']",
            ".post-time-wrapper input.d-text",
        ],
        # 定时开关打开后的时间显示框（须点击才呼出日期时间浮层）
        "SCHEDULE_TIME_DISPLAY": [
            ".post-time-wrapper input[type='text']",
            ".post-time-wrapper input.d-text",
            ".post-time-wrapper .d-datepicker-input input",
            ".post-time-wrapper .d-datepicker-input",
        ],
        "SCHEDULE_DATE_PICKER": [
            "body > .post-time-date-picker-popover-class",
            ".post-time-date-picker-popover-class",
        ],
        # 图文旧版 / fallback
        "PRIVACY_PUBLIC": [
            "label:has-text('公开')",
            "div[class*='radio']:has-text('公开')",
        ],
        "PRIVACY_PRIVATE": [
            "label:has-text('私密')",
            "div[class*='radio']:has-text('私密')",
        ],
        "PUBLISH_SCHEDULE": [
            ".post-time-wrapper",
            ".post-time-wrapper .custom-switch-card",
            "label:has-text('定时发布')",
            "div[class*='radio']:has-text('定时发布')",
            "input[type='checkbox'][class*='schedule']",
        ],
        "SCHEDULE_INPUT": [
            ".post-time-wrapper input[type='text']",
            "input[placeholder*='日期']",
            "input[placeholder*='时间']",
            "input[type='datetime-local']",
        ],
        # 步骤7：图文专属开关
        "ALLOW_CO_CREATE_LABEL": [
            "text=允许合拍",
            "*:has-text('允许合拍')",
        ],
        "ALLOW_COPY_CONTENT_LABEL": [
            "text=允许正文复制",
            "*:has-text('允许正文复制')",
            "*:has-text('正文复制')",
        ],
        # 步骤6C：添加地点
        "LOCATION_INPUT": [
            "input[placeholder*='位置']",
            "input[placeholder*='地点']",
            "div[class*='location'] input",
        ],
        # 步骤6A/6B：视频发布「内容设置」区（20260525 DOM 报告）
        "CONTENT_SETTINGS_SECTION": [
            ".publish-page-content-content-extra",
        ],
        "WORK_ORIGINAL_LABEL": [
            ".original-wrapper",
            ".original-wrapper .custom-switch-text-content",
            "text=原创声明",
            "*:has-text('原创声明')",
        ],
        "ORIGINAL_DECLARATION_CHECKBOX": [
            ".publish-page-content-content-extra .original-wrapper input[type='checkbox']",
            ".original-wrapper input[type='checkbox']",
            "xpath=//*[normalize-space()='原创声明']/ancestor::div[1]//input[@type='checkbox']",
            "xpath=//*[normalize-space()='原创声明']/ancestor::div[2]//input[@type='checkbox']",
            "xpath=//*[normalize-space()='原创声明']/ancestor::div[3]//input[@type='checkbox']",
            "xpath=//*[normalize-space()='原创声明']/ancestor::div[4]//input[@type='checkbox']",
            "text=原创声明 >> xpath=../..//input[@type='checkbox']",
        ],
        "ORIGINAL_DECLARATION_SWITCH": [
            ".original-wrapper .d-switch-simulator",
            ".original-wrapper .d-clickable.d-switch",
            ".original-wrapper .custom-switch-card",
        ],
        # 步骤6A：开启原创声明时的权益确认弹窗（需勾选协议后点确认）
        "ORIGINAL_DECLARATION_DIALOG": [
            "div[role='dialog']:has-text('笔记完成原创声明后')",
            "div.d-modal:has-text('笔记完成原创声明后')",
            "div.d-modal-wrapper:has-text('笔记完成原创声明后')",
            "div:has-text('笔记完成原创声明后'):has(button:has-text('声明原创'))",
            "div:has-text('笔记完成原创声明后'):has(button:has-text('申明原创'))",
            "div:has-text('获得原创笔记标记'):has(button)",
            "div:has-text('原创声明须知'):has(button:has-text('声明原创'))",
            "div:has-text('原创声明须知'):has(button:has-text('申明原创'))",
        ],
        "ORIGINAL_DECLARATION_AGREEMENT": [
            "label:has-text('我已阅读并同意')",
            "div:has-text('我已阅读并同意') input[type='checkbox']",
            "div[role='dialog'] label:has-text('我已阅读并同意')",
            "div.d-modal label:has-text('我已阅读并同意')",
            "div:has-text('笔记完成原创声明后') label:has-text('我已阅读并同意')",
            "div:has-text('原创声明须知') >> xpath=..//label[contains(.,'我已阅读')]",
        ],
        "ORIGINAL_DECLARATION_CONFIRM_BTN": [
            "button:has-text('声明原创')",
            "button:has-text('申明原创')",
            "div[role='dialog'] button:has-text('声明原创')",
            "div[role='dialog'] button:has-text('申明原创')",
            "div.d-modal button:has-text('声明原创')",
            "div.d-modal button:has-text('申明原创')",
        ],
        "CONTENT_TYPE_DECLARATION_ENTRY": [
            ".publish-page-content-content-extra .d-select-wrapper:has-text('添加内容类型声明')",
            ".publish-page-content-content-extra .d-select-wrapper >> text=添加内容类型声明",
            "text=添加内容类型声明",
            "div:has-text('添加内容类型声明')",
            "span:has-text('添加内容类型声明')",
        ],
        "CONTENT_TYPE_DECLARATION_PANEL": [
            "body > .d-popover.d-dropdown:has-text('虚构演绎，仅供娱乐')",
            "body > .d-popover.d-dropdown >> text=虚构演绎，仅供娱乐",
            "div[role='dialog']:has-text('内容类型声明')",
            "div[role='dialog']:has-text('添加内容类型声明')",
            "div[class*='modal']:has-text('内容类型声明')",
            "div[class*='dialog']:has-text('内容类型声明')",
            "div[class*='popover']:has-text('内容类型声明')",
            "div[class*='dropdown']:has-text('虚构演绎')",
        ],
        "CONTENT_TYPE_DECLARATION_PANEL_ANCHOR": [
            "虚构演绎，仅供娱乐",
        ],
        "CONTENT_TYPE_DECLARATION_CONFIRM": [
            "button:has-text('确定')",
            "button:has-text('完成')",
            "button:has-text('确认')",
            "div:has-text('确定')",
        ],
        "WORK_CONTENT_ATTR_HINT": [
            "text=内容属性",
            "text=笔记类型",
            "text=内容类型声明",
            "text=添加内容类型声明",
        ],
    }
