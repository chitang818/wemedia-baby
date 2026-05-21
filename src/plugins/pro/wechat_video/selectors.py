"""
视频号插件 CSS/XPath 选择器集中配置
文件路径: src/plugins/pro/wechat_video/selectors.py

所有发布步骤相关选择器均按功能分组，与标准化目录规范一致。
候选顺序对齐 docs/03插件系统/3.2插件选择器标准化规范.md 与
docs/03插件系统/AI分析报告/视频号_视频发布_DOM 分析报告_20260330.md：
语义/文案/placeholder 优先，具体 class 兜底（页面多为 wujie Shadow 内 weui 组件）。

步骤失败时可根据报错定位到对应键名，对照文档更新 DOM 即可快速排查。
"""


class Selectors:
    # ==========================================
    # 1. 登录相关选择器 (Login)
    # ==========================================
    LOGIN = {
        # 登录按钮
        "LOGIN_BTN": ["button.login-btn", ".login-btn"],
        # 二维码区域
        "QR_CODE": [
            ".qr-code-container", ".qrcode-container", "img.qrcode",
            "div[class*='qrcode']", ".login_content_qrcode",
            ".login_qrcode_content", ".qrcode iframe",
        ],
        # 手机号输入框
        "PHONE_INPUT": ["input[type='tel']", "input[placeholder*='手机']"],
        # 密码输入框
        "PASSWORD_INPUT": ["input[type='password']"],
        # 提交按钮
        "SUBMIT_BTN": ["button.submit-btn", "button[type='submit']"],
    }

    # 用户信息提取
    USER_INFO = {
        # 头像
        "AVATAR": [
            "div[class*='avatar']", "img[class*='avatar']",
            ".finder-avatar", ".header-avatar", ".user-avatar",
            "img[src*='head']",
        ],
        # 用户资料区
        "USER_PANEL": [
            "div[class*='user-info']", "div[class*='userInfo']",
            ".finder-info", ".header-info", ".profile-info",
        ],
        # 昵称
        "NICKNAME": [
            "span[class*='nickname']", "div[class*='nickname']",
            ".finder-nickname", ".header-name", ".account-name", ".user-name",
        ],
    }

    # 登录成功判定指标（用于脚本检测）
    LOGIN_INDICATORS = [
        "div[class*='user-info']", "div[class*='userInfo']",
        ".finder-info", ".header-info",
        ".avatar", ".user-avatar", ".finder-avatar", "img[src*='head']",
        ".nickname", ".finder-nickname", ".header-name", ".account-name",
        ".profile-info", ".user-center", ".user-name",
    ]

    # 登录检测关键 Cookie 名
    REQUIRED_COOKIES = ["wxuin", "sessionid"]

    # ==========================================
    # 2. 首页入口与发布导航 (Home)
    # ==========================================
    HOME = {
        # 创作者中心入口
        "CREATOR_CENTER": ["a[href*='channels']", "a[href*='platform']"],
        # 发布入口按钮（通用）
        "PUBLISH_ENTRY": [
            "button.weui-desktop-btn_primary:has-text('发表')",
            "button[class*='publish']", "button:has-text('发布')",
        ],
        # ✅ 已确认：视频发布入口按钮
        # 真实 DOM：<button type="button" class="weui-desktop-btn weui-desktop-btn_primary">发表视频</button>
        "PUBLISH_VIDEO_BTN": [
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('发表视频')",
        ],
        # 图文发布入口（待采集精确选择器）
        "PUBLISH_IMAGE_BTN": [
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('发表图文')",
        ],
        # ✅ 已确认：视频发布页加载完成标识（上传视频区域出现）
        # 真实 DOM：<div class="upload-content">...<span class="add-icon weui-icon-outlined-add">...</span>...</div>
        "VIDEO_PUBLISH_PAGE_MARKER": [
            "div.upload-content",
            "span.add-icon.weui-icon-outlined-add",
        ],
    }

    # ==========================================
    # 3. 视频/图文内容发布 (Publish)
    # ==========================================
    PUBLISH = {
        # 步骤3：文件上传（L1：与 DOM 报告一致，优先 button 文案「上传…」；Shadow 内外均可能命中）
        "FILE_INPUT": ["input[type='file']"],
        # ✅ 已确认：上传视频区域（点击触发 file chooser）
        "UPLOAD_BTN": [
            "button:has-text('上传时长')",
            "button:has-text('上传')",
            "div.upload-content",
            "span.add-icon.weui-icon-outlined-add",
        ],
        # ✅ 已确认：上传成功标识 — 出现「删除」按钮即表示视频已上传
        # 真实 DOM：<div class="finder-tag-wrap"><div class="tag-inner">删除</div></div>
        "UPLOAD_SUCCESS_MARKER": [
            "div.finder-tag-wrap div.tag-inner:has-text('删除')",
            "div.tag-inner:has-text('删除')",
        ],

        # ===== 步骤4：封面设置（所有元素在 wujie-app Shadow DOM 内） =====
        # ✅ 已确认：封面入口 — 点击打开编辑封面弹窗
        # 真实 DOM：<div class="cover-tips">个人主页和分享卡片(3:4)</div>
        "COVER_ENTRY": "div.vertical-cover-wrap.img-popover-wrap > div.tips-wrap > div.cover-tips",
        # ✅ 已确认：编辑封面弹窗
        "COVER_DIALOG": "div.edit-cover-dialog-container > div > div.weui-desktop-dialog__wrp > div",
        # ✅ 已确认：弹窗内上传封面按钮（+号区域）
        "COVER_UPLOAD_BTN": "div.single-cover-uploader-wrap > div.wrap > div.img-wrap.initial-wrap",
        # ✅ 已确认：弹窗内确认按钮
        "COVER_CONFIRM_BTN": "div.weui-desktop-dialog__ft button.weui-desktop-btn_primary.weui-desktop-btn_mini",

        # 步骤5A：图文标题输入框（仅图文发布页存在）
        "IMAGE_TITLE_INPUT": 'input.weui-desktop-form__input[placeholder*="填写标题"]',
        "IMAGE_TITLE_INPUT_CANDIDATES": [
            'div.form-item.cell-center input.weui-desktop-form__input[placeholder*="填写标题"]',
            'input.weui-desktop-form__input[placeholder*="填写标题"]',
        ],

        # 步骤5：标题输入框（视频号视频页暂无独立标题框，标题在描述中）
        "TITLE_INPUT": ["input[placeholder*='标题']", ".title-input"],
        # ✅ 步骤5 视频描述（DOM 报告 L1：placeholder「添加描述」+ contenteditable）
        "DESC_EDITOR": "div.post-desc-box div.input-editor[contenteditable]",
        "DESC_EDITOR_CANDIDATES": [
            'div.input-editor[contenteditable][data-placeholder="添加描述"]',
            "div.post-desc-box div.input-editor[contenteditable]",
        ],
        # 步骤5：话题输入
        "TOPIC_INPUT": ["input[placeholder*='话题']"],

        # ===== 步骤6：位置设置（所有元素在 wujie-app Shadow DOM 内） =====
        # ✅ 已确认：位置下拉框入口
        "LOCATION_DROPDOWN": "div.post-position-wrap > div.position-display > div",
        # ✅ 已确认：「不显示位置」选项
        "LOCATION_HIDE_OPTION": "div.location-item div.name",
        # ✅ 已确认：验证「不显示位置」已选中
        "LOCATION_HIDE_VERIFY": "div.position-display div.not-display > span",

        # ===== 步骤7：链接/购物车（wujie Shadow 内，见 视频号_购物车功能 DOM 分析报告_20260402.md） =====
        # 步骤1：展开链接类型下拉（勿点 choosen-link-wrap，仅初始「选择链接」用 link-display-wrap）
        "LINK_DISPLAY_WRAP": "div.post-link-wrap div.link-display-wrap",
        # 步骤2：下拉项「商品」
        "LINK_OPTION_ITEM": "div.link-option-item",
        # 步骤3：打开商品选择弹窗（可点击区为 content-wrap）
        "LINK_PRODUCT_CHOOSE_CONTENT": "div.post-link-wrap div.link-input-wrap div.post-component-choose-wrap div.content-wrap",
        "LINK_INPUT_WRAP": "div.post-link-wrap div.link-input-wrap",
        # 步骤3～8：弹窗 add-commodity-dialog（关闭后仍存在，display:none）
        "LINK_COMMODITY_DIALOG": "div.add-commodity-dialog",
        # 搜索框 placeholder「请输入商品名称/编码搜索」，class 常含 ignore_default_input
        "LINK_COMMODITY_SEARCH_INPUT": 'div.add-commodity-dialog input[placeholder*="商品名称"]',
        # 筛选：.search-btn 内的 button（weui-desktop-btn_default）
        "LINK_COMMODITY_FILTER_BTN": "div.add-commodity-dialog div.search-btn button",
        # 表格行 / 单选
        "LINK_COMMODITY_TABLE_ROWS": "div.add-commodity-dialog .ant-table-tbody tr",
        "LINK_COMMODITY_RADIO": "div.add-commodity-dialog input.ant-radio-input",
        # 底部主按钮「添加」或「添加 (1)」（选中后启用，勿点禁用态）
        "LINK_COMMODITY_ADD_BTN_PRIMARY": "div.add-commodity-dialog button.weui-desktop-btn_primary",
        # 完成后链接区展示
        "LINK_CHOOSEN_WRAP": "div.post-link-wrap div.choosen-link-wrap",

        # ===== 步骤8：定时发表设置（所有元素在 wujie-app Shadow DOM 内） =====
        # DOM 报告优先：get_by_role(radio, name='定时')；工程内等价为先文案「定时」再 value
        "SCHEDULE_RADIO": ".weui-desktop-form__radio[value='1']",
        # ✅ 已确认：「不定时」单选按钮（value="0"）
        "SCHEDULE_RADIO_IMMEDIATE": ".weui-desktop-form__radio[value='0']",
        # ✅ 已确认：发表时间输入框（readonly，仅用于触发面板弹出和验证）
        "SCHEDULE_TIME_INPUT": ".weui-desktop-picker__date-time .weui-desktop-form__input",
        # ✅ 已确认：日期时间选择器整体容器
        "SCHEDULE_DATE_PICKER": ".weui-desktop-picker__date-time",
        # ✅ 已确认：日期面板弹出层（默认 display:none）
        "SCHEDULE_DATE_PANEL": ".weui-desktop-picker__date-time > .weui-desktop-picker__dd",
        # ✅ 已确认：日期面板点击触发器（dt 元素）
        "SCHEDULE_DATE_TRIGGER": ".weui-desktop-picker__date-time .weui-desktop-picker__dt",
        # ✅ 已确认：年月标签（第1个=年，第2个=月）
        "SCHEDULE_YEAR_MONTH_LABEL": ".weui-desktop-picker__panel__label",
        # ✅ 已确认：上一月按钮（当月无法往前时 display:none）
        "SCHEDULE_PREV_MONTH": ".weui-desktop-btn__icon__left",
        # ✅ 已确认：下一月按钮
        "SCHEDULE_NEXT_MONTH": ".weui-desktop-btn__icon__right",
        # ✅ 已确认：所有日期单元格（a 标签）
        "SCHEDULE_DATE_CELLS": ".weui-desktop-picker__table-row td a",
        # ✅ 已确认：时间面板弹出层（默认 display:none）
        "SCHEDULE_TIME_PANEL": ".weui-desktop-picker__dd__time",
        # ✅ 已确认：时间面板触发器（dt 元素）
        "SCHEDULE_TIME_TRIGGER": ".weui-desktop-picker__time .weui-desktop-picker__dt",
        # ✅ 已确认：小时列表容器（0-23）
        "SCHEDULE_HOUR_LIST": ".weui-desktop-picker__time__hour",
        # ✅ 已确认：分钟列表容器（0-59）
        "SCHEDULE_MINUTE_LIST": ".weui-desktop-picker__time__minute",

        # ===== 步骤9：短标题设置（所有元素在 wujie-app Shadow DOM 内） =====
        # ✅ 已确认：短标题输入框
        # 真实 DOM：<input type="text" placeholder="概括视频主要内容，字数建议6-16个字符" class="weui-desktop-form__input">
        # 父容器：div.form-item-body.short-title-wrap
        "SHORT_TITLE_INPUT": "div.short-title-wrap input.weui-desktop-form__input",

        # ===== 步骤10：声明原创（所有元素在 wujie-app Shadow DOM 内） =====
        # ✅ 已确认：页面上的声明原创复选框（主复选框）
        # 父容器：div:nth-child(8) > div.form-item-body
        "ORIGINAL_CHECKBOX": "div.form-item-body .ant-checkbox-input",
        # ✅ 已确认：弹出的「原创权益」弹窗容器
        "ORIGINAL_DIALOG": "div.declare-original-dialog .weui-desktop-dialog",
        # ✅ 已确认：弹窗内的「我已阅读并同意」协议复选框
        "ORIGINAL_DIALOG_AGREE_CHECKBOX": "div.declare-original-dialog .original-proto-wrapper .ant-checkbox-input",
        # ✅ 已确认：弹窗内的「声明原创」确认按钮（勾选协议后才可点击）
        "ORIGINAL_DIALOG_CONFIRM_BTN": "div.declare-original-dialog .weui-desktop-dialog__ft div:nth-child(2) button",

        # ===== 发表步骤附属：点击「发表」后可能出现的「广告分成 / 创作分成计划」引导弹窗 =====
        # 文案含「声明原创的视频有机会获得广告分成」等；未勾选任务「声明原创」时点「直接发表」。
        # 实现见 step_09_submit._handle_post_submit_original_revenue_modal（遍历主文档 + wujie shadow 内 .weui-desktop-dialog）

        # 发表按钮（Shadow 内 querySelector 仅能用标准 CSS，勿写 Playwright 专有 :has-text）
        # DOM 报告 L1 由 step_09_submit 内 page.get_by_role('button', name='发表') 优先尝试
        "SUBMIT_BTN": [
            "div.form-btns > div:nth-child(5) > span > div > button.weui-desktop-btn.weui-desktop-btn_primary",
            "div.form-btns > div:nth-child(5) > span > div > button",
            "div.form-btns button.weui-desktop-btn.weui-desktop-btn_primary",
            "button.weui-desktop-btn.weui-desktop-btn_primary",
            "div.form-btns > div > span > div > button.weui-desktop-btn",
        ],
    }

    # ==========================================
    # 4. 风控及异常 (Security)
    # ==========================================
    SECURITY = {
        # 风控/账号异常弹窗（待采集精确选择器）
        "RISK_MODAL": ["div[role='dialog']:has-text('异常')"],
        # 发布失败 Toast（待采集精确选择器）
        "PUBLISH_TOAST_ERROR": [".toast:has-text('失败')"],
        # 操作频繁 Toast（待采集精确选择器）
        "PUBLISH_TOAST_FREQ": [".toast:has-text('频繁')"],
    }

    # ==========================================
    # 5. 发布结果验证 (Verify)
    # ==========================================
    VERIFY = {
        # 发布成功标识（Toast文字包含"已发表"）
        "SUCCESS_TOAST": "span:has-text('已发表')",
        # 管理页特征（发布成功后通常跳转到管理页）
        "MANAGE_PAGE_INDICATOR": ["div:has-text('作品管理')"],
    }

    # ==========================================
    # 6. 发布设置 (Settings)
    # ==========================================
    SETTINGS = {
        # 可见性设置（待采集精确选择器）
        "PRIVACY_PUBLIC": [],
        "PRIVACY_PRIVATE": [],
        # 定时发布（待采集精确选择器）
        "PUBLISH_SCHEDULE": [],
        "SCHEDULE_INPUT": [],
    }
