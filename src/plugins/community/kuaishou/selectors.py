"""
快手插件 CSS/XPath 选择器集中配置
文件路径: src/plugins/community/kuaishou/selectors.py

基于 WeMedia X-Ray 分析报告（20260306_200613 快手发布流程分析）更新。
所有选择器与 cp.kuaishou.com/article/publish/video 页面实际 DOM 对照。

X-Ray 确认:
  - 会话 Cookie: userId, bUserId, kuaishou.web.cp.api_st, kuaishou.web.cp.api_ph
  - 发布按钮: div.publish-button ✅（count=1, visible）
  - 未登录时跳转链: cp.kuaishou.com/rest/infra/logout → passport.kuaishou.com/pc/account/login
  - 上传 API: upload.kuaishouzt.com/api/upload/fragment（分片上传）
  - 上传完成 API: /rest/cp/works/v2/video/pc/upload/finish
"""


class Selectors:
    # ==========================================
    # 1. 登录与基础信息 (Login & User Info)
    # ==========================================
    LOGIN = {
        "QR_CODE": ["canvas[class*='qr']", "img[class*='qr']", "[class*='二维码']"],
        "LOGIN_BTN": ["button:has-text('登录')", "[class*='login-btn']"],
    }

    USER_INFO = {
        "NICKNAME": [
            "[class*='nickname']",
            "[class*='user-name']",
            ".user-info .name",
            "[class*='userInfo'] span",
        ],
        "AVATAR": ["[class*='avatar']", "img[class*='avatar']"],
    }

    # X-Ray 确认: 登录后实际会话 Cookie（注意用"点号"分隔）
    REQUIRED_COOKIES = ["userId", "kuaishou.web.cp.api_st"]
    SESSION_COOKIES = [
        "userId",
        "bUserId",
        "kuaishou.web.cp.api_st",
        "kuaishou.web.cp.api_ph",
    ]

    # ==========================================
    # 2. 首页/发布页容器
    # ==========================================
    HOME = {
        "PUBLISH_VIDEO_BTN": [
            "a[href*='article/publish/video']",
            "a:has-text('发布视频')",
            "button:has-text('发布视频')",
            "[class*='publish']:has-text('发布视频')",
            "[class*='publish']:has-text('发布')",
        ],
        "VIDEO_PUBLISH_PAGE_MARKERS": [
            "#root-video-publish",
            "#joyride-wrapper",
            "div.publish-button",
            "[class*='_publish-container_']",
            "input[type='file']",
        ],
        # 图文发布入口 —— DOM 报告 20260403 步骤1：顶部导航「发布作品」下拉路径
        # 路径：点「发布作品」(e39) → 展开下拉 → 点「发布图文」(e512)
        "PUBLISH_WORK_BTN": [
            "text=发布作品",
            "[class*='publish']:has-text('发布作品')",
            "button:has-text('发布作品')",
        ],
        "PUBLISH_IMAGE_BTN": [
            "text=发布图文",
            "[class*='menu']:has-text('发布图文')",
            "[role='menuitem']:has-text('发布图文')",
        ],
        # 图文发布页 Tab —— ref=e82，tablist 内「上传图文」
        "IMAGE_PUBLISH_TAB": [
            "[role='tab']:has-text('上传图文')",
            "div[role='tab']:has-text('上传图文')",
        ],
        # 图文发布页加载成功特征元素（未上传图片时显示）
        "IMAGE_PUBLISH_PAGE_MARKERS": [
            "text=拖拽图片到此或点击上传",
            "[role='button']:has-text('上传图片')",
            "button:has-text('上传图片')",
            "text=支持最多 31 张",
        ],
        # 「还有上次未发布的图集，是否继续编辑？」恢复弹窗
        "IMAGE_DRAFT_RECOVERY_DIALOG": [
            "text=还有上次未发布的图集",
            "[role='dialog']:has-text('未发布')",
        ],
        "IMAGE_DRAFT_DISCARD_BTN": [
            "button:has-text('放弃')",
            "text=放弃",
        ],
    }

    # X-Ray: 未登录跳转判据
    REDIRECT = {
        "LOGIN_URLS": ["passport.kuaishou.com", "/rest/infra/logout", "login", "signin"],
    }

    # ==========================================
    # 3. 发布页元素
    # ==========================================
    PUBLISH = {
        # 文件输入
        "FILE_INPUT": [
            "#joyride-wrapper input[type='file']",
            "[class*='_publish-container_'] input[type='file']",
            "input[type='file'][accept*='video']",
            "input[type='file']",
        ],
        # 上传区域
        "UPLOAD_BTN": [
            "#joyride-wrapper",
            "[class*='_publish-container_']",
            "div[class*='upload']",
        ],
        # 上传成功标志（视频）
        "UPLOAD_SUCCESS_MARKER": [
            "[class*='_preview-btns_']",
            "div:has-text('重新上传')",
            "[class*='_button-default_']:has-text('重新上传')",
            "div.publish-button",
        ],
        # 图片上传入口按钮 —— X-Ray DOM 实测：button._upload-btn_ysbff_57「上传图片」
        # 点击该按钮触发 File Chooser，页面监听 chooser 事件完成上传（与视频机制一致）
        "IMAGE_UPLOAD_BTN": [
            "button._upload-btn_ysbff_57",
            "button[class*='_upload-btn_ysbff']",
            "section._upload-container_ysbff_12 button",
            "button:has-text('上传图片')",
            "[class*='_upload-text_ysbff'] button",
        ],
        # 图片上传 file input —— 图文发布页（tabType=2）专用
        # X-Ray 20260403 实测结论：
        #   - 图片 input: accept="image/png, image/jpg, image/jpeg, image/webp", multiple=True
        #   - 视频 input: accept="video/*,...", multiple=False
        #   - 两个 input 都位于同一页面；图片 input 在 #rc-tabs-0-panel-2（图文 Tab 面板）内
        #   - 首选用 panel-2 ID 限定范围，避免命中视频 input
        #   - 图片 input 支持 multiple=True，可一次性传多张图片
        "IMAGE_FILE_INPUT": [
            "#rc-tabs-0-panel-2 input[type='file']",
            "input[type='file'][accept*='image/png']",
            "input[type='file'][accept*='image/jpg']",
            "input[type='file'][accept*='image/jpeg']",
            "input[type='file'][accept*='image/webp']",
            "input[type='file']:not([accept*='video'])",
        ],
        # 图片上传成功标志：出现「编辑图片」区域 + 图片数量（如 1/31）
        "IMAGE_UPLOAD_SUCCESS_MARKER": [
            "text=编辑图片",
            "[class*='edit']:has-text('编辑图片')",
        ],
        # 标题输入
        "TITLE_INPUT": [
            "input[placeholder*='标题']",
            "textarea[placeholder*='标题']",
            "input[class*='title']",
        ],
        # 描述输入框
        # DOM 分析报告 20260403：稳定 id=work-description-edit，优先使用；
        # class 带哈希后缀（_description_17g9x_24）易碎，仅作兜底；
        # 避免使用 div[contenteditable='true'] 等宽泛选择器误匹配其他元素
        "DESC_EDITOR": [
            "#work-description-edit",
            "[class*='_description_'][contenteditable='true']",
            "[class*='_edit-desc-container_'] [contenteditable='true']",
            "[class*='_caption-v2-container_'] [contenteditable='true']",
        ],
        "DESC_PLACEHOLDER": [
            "#work-description-edit",
            "[class*='_description_']",
            "div[placeholder*='作品描述']",
        ],
        # 作品描述 # 触发的话题下拉（须在 _edit-desc-container_ 内，勿用全局 role=listbox 以免误判 Ant Select）
        "TOPIC_DROPDOWN": [
            "[class*='_edit-desc-container_'] [class*='_dropdown-container_']",
            "[class*='_edit-desc-container_'] [class*='_desc-dropdown_']",
            "[class*='_caption-v2-container_'] [class*='_dropdown-container_']",
            "[class*='_caption-v2-container_'] [class*='_desc-dropdown_']",
            "[class*='_desc-dropdown_']",
        ],
        "TOPIC_SUGGESTION": [
            "[class*='_edit-desc-container_'] [class*='_topic-item_']",
            "[class*='_caption-v2-container_'] [class*='_topic-item_']",
            "[class*='_desc-dropdown_'] [class*='_topic-item_']",
        ],
        "TOPIC_SUGGESTION_ACTIVE": [
            "[class*='_edit-desc-container_'] [class*='_topic-item_'][class*='_active_']",
            "[class*='_caption-v2-container_'] [class*='_topic-item_'][class*='_active_']",
            "[class*='_desc-dropdown_'] [class*='_topic-item_'][class*='_active_']",
        ],
        # 已收成话题：诊断页 CSS 为 .at-tag-item（蓝色 #385080），纯文本 # 不算
        "TOPIC_CHIP": [
            "#work-description-edit .at-tag-item",
            "[class*='_edit-desc-container_'] .at-tag-item",
            "[class*='_caption-v2-container_'] .at-tag-item",
        ],
        "TOPIC_AI_BUTTON": [
            "#ai-bar-container :text('智能话题')",
            "[class*='_ai-button-icon-topic']",
            "[id='ai-bar-container'] [id='ai-button']:has([class*='icon-topic'])",
        ],
        # DOM 对照表 §11：发布逻辑在底部栏「主色 div」上；div.publish-button 可能只是可见外壳，须优先点 _button-primary_
        "SUBMIT_BTN": [
            "[class*='_edit-section-btns_'] [class*='_button-primary_']:has-text('发布')",
            "[class*='_edit-section-btns_'] [class*='_button-primary_']",
            "._edit-section-btns_ql0z6_118 ._button-primary_3a3lq_60",
            "#joyride-wrapper > main > div._edit-container_ql0z6_7 > div._edit-section_ql0z6_20._last_ql0z6_26 > div._edit-section-form_ql0z6_100 > div._edit-section-btns_ql0z6_118 > div._button_3a3lq_1._button-primary_3a3lq_60",
            "[class*='_edit-section-btns_'] div.publish-button",
            "div.publish-button:has-text('发布作品')",
            "div.publish-button",
        ],
    }

    # ==========================================
    # 4. 风控及异常
    # ==========================================
    SECURITY = {
        "RISK_MODAL": ["[role='dialog']:has-text('账号异常')", "[class*='risk']"],
        "PUBLISH_TOAST_ERROR": ["[class*='toast']:has-text('失败')", "[class*='error']"],
        "PUBLISH_TOAST_FREQ": ["[class*='频繁']", ":has-text('操作频繁')"],
    }

    # ==========================================
    # 5. 结果验证
    # ==========================================
    VERIFY = {
        # 步骤 11 用 SUCCESS_TOAST_PHRASES / CONTAINERS；保留旧键供脚本或外部引用
        "SUCCESS_TOAST": "text='发布成功'",
        "MANAGE_PAGE_INDICATOR": ["**/article/manage**"],
        # 与 README 一致：快手实际多为「发布成功」；「内容发布成功」为兼容
        "SUCCESS_TOAST_PHRASES": [
            "内容发布成功",
            "视频发布成功",
            "发布作品成功",
            "发布成功",
        ],
        "SUCCESS_TOAST_CONTAINERS": [
            ".ant-message-notice-content",
            ".ant-notification-notice-description",
            ".ant-message",
            "[class*='toast']",
            "[class*='message']",
        ],
    }

    # ==========================================
    # 6. 发布设置
    # ==========================================
    # 步骤10 仅设置发布时间（定时/立即），不操作互动设置、不操作查看权限；故不提供 PRIVACY_* 避免误点
    SETTINGS = {
        # 定时发布：仅限「发布时间」区域内、包裹 input[value="2"] 的 label；禁止用无范围选择器，否则会误点到「查看权限」的 value=2（好友可见）
        "PUBLISH_SCHEDULE": [
            "#setting-tours div[class*='_publish-time_'] div.ant-radio-group label.ant-radio-wrapper:has(input[value='2'])",
            "#setting-tours div[class*='_edit-form-item_'] div[class*='_publish-time_'] div.ant-radio-group label:has(input[value='2'])",
            "#setting-tours div[class*='_publish-time_'] div.ant-radio-group-outline label.ant-radio-wrapper:has(input[value='2'])",
            # 图文发布页没有 #setting-tours，用更通用的发布时间区选择器兜底
            "div[class*='_publish-time_'] div.ant-radio-group label.ant-radio-wrapper:has(input[value='2'])",
            "div[class*='_publish-time_'] div.ant-radio-group label:has(input[value='2'])",
            "div[class*='_publish-time_'] label.ant-radio-wrapper:has(input[value='2'])",
        ],
        "PUBLISH_NOW": [
            "label.ant-radio-wrapper:has-text('立即发布')",
            # AI DOM: 发布时间 radio (value=1 => 立即发布)
            ".ant-radio-input[value='1']",
        ],
        # 定时发布：日期时间选择器与确认（AI DOM）
        "PUBLISH_TIME_INPUT": [
            ".ant-picker._data-picker_171ix_411 input",
            ".ant-picker._data-picker_171ix_411 input[placeholder*='选择日期时间']",
            "[class*='_publish-time_'] .ant-picker input[placeholder*='选择日期时间']",
        ],
        "PUBLISH_TIME_DROPDOWN": [
            ".ant-picker-dropdown",
        ],
        # 弹层内「确定」须点在 button 上（文档 10.3.4）；优先带 :not(.ant-picker-dropdown-hidden) 限定当前可见弹层
        "PUBLISH_TIME_OK": [
            ".ant-picker-dropdown:not(.ant-picker-dropdown-hidden) .ant-picker-ok button",
            ".ant-picker-dropdown:not(.ant-picker-dropdown-hidden) .ant-picker-footer button.ant-btn-primary",
            "#setting-tours .ant-picker-dropdown:not(.ant-picker-dropdown-hidden) .ant-picker-ok button",
            "[class*='_publish-time_'] .ant-picker-dropdown:not(.ant-picker-dropdown-hidden) .ant-picker-ok button",
            ".ant-picker-ok button",
            ".ant-picker-panel-container .ant-picker-ok button",
        ],
    }

    # 使用向导（作品信息 1/4 等）：发布页可能出现的引导弹窗，需关闭后再操作
    WIZARD = {
        "WORK_INFO_MODAL": [
            "div[role='dialog']:has-text('作品信息')",
            "[class*='modal']:has-text('作品信息')",
            "[class*='joyride']:has-text('作品信息')",
            ":has-text('1/4'):has-text('作品信息')",
        ],
        "WIZARD_NEXT_OR_DONE": [
            "button:has-text('下一步')",
            "button:has-text('知道了')",
            "button:has-text('完成')",
            "button:has-text('跳过')",
            "xpath=//button[contains(., '下一步') or contains(., '知道了') or contains(., '完成') or contains(., '跳过')]",
        ],
        "WIZARD_CLOSE_X": [
            "div[role='dialog']:has-text('作品信息') >> button[aria-label='关闭']",
            "div[role='dialog']:has-text('作品信息') >> [class*='close']",
            "[class*='modal']:has-text('作品信息') >> button:has-text('×')",
            "div[role='dialog'] >> button >> nth=-1",
        ],
    }

    # 封面设置区域
    COVER = {
        "COVER_SECTION": ["[class*='_high-cover-editor_']", "[class*='_high-cover-editor-label_']"],
        "COVER_FULL_EDITOR": ["[class*='_cover-full-editor_']", "[class*='_default-cover_']"],
    }

    # ==========================================
    # 7. 作品申明 / 作者声明（步骤8）
    # ==========================================
    # 作者声明 Ant Design Select（OpenClaw DOM 20260526）
    WORK_DECLARATION = {
        "LABEL_TEXT": "作者声明",
        "PLACEHOLDER": "为作品添加补充说明",
        "COMBOBOX_BY_LABEL": [
            'label:has-text("作者声明")',
        ],
        "DROPDOWN_VISIBLE": [
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden)",
        ],
        "LISTBOX": [
            '[role="listbox"]',
        ],
        "SELECTION_ITEM": [
            ".ant-select-selection-item",
        ],
        "OPTION_BY_LABEL_ATTR": [
            '[role="option"][label="{text}"]',
        ],
    }

    # ==========================================
    # 8. 作者服务（步骤6）
    # ==========================================
    AUTHOR_SERVICE = {
        # 作者服务区域中「选择服务类型」下拉触发器
        "SERVICE_TYPE_TRIGGER": [
            "div[class*='_author-service_'] div[class*='ant-select']:not([class*='disabled'])",
            "div[class*='_author-service_'] .ant-select-selector",
            ".ant-select:has(.ant-select-selection-placeholder:has-text('选择服务类型'))",
            ".ant-select-selector:has(.ant-select-selection-placeholder:has-text('选择服务类型'))",
        ],
        # 下拉选项中「关联商品」条目
        "OPTION_GOODS": [
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item:has-text('关联商品')",
            ".ant-select-item-option:has-text('关联商品')",
            "li:has-text('关联商品')",
        ],
        # 商品名称输入框（「关联商品获得更多收入」placeholder）
        "GOODS_INPUT": [
            "input[placeholder*='关联商品获得更多收入']",
            "input[placeholder*='关联商品']",
            "div[class*='_author-service_'] .ant-select:nth-of-type(2) input",
            "div[class*='_author-service_'] .ant-select-show-search input",
        ],
        # 商品搜索结果卡片（下拉出现后的第一个商品卡）
        "GOODS_RESULT_CARD": [
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item:first-child",
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option:first-child",
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden) [class*='goods-item']:first-child",
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden) [class*='product-item']:first-child",
            ".ant-select-item:first-child",
        ],
    }
