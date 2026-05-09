"""
抖音插件 CSS/XPath 选择器集中配置
文件路径: src/plugins/community/douyin/selectors.py

所有发布步骤相关选择器均为「唯一匹配」，与 docs/03插件系统/01抖音插件/3.1.4抖音插件DOM对照表.md 一致。
步骤失败时可根据报错定位到对应键名，对照文档更新 DOM 即可快速排查。
图文上传成功判定键：`PUBLISH["IMAGE_UPLOAD_SUCCESS_MARKER"]`（「已添加N张图片/继续添加」，以及「清空并重新上传」等上传成功相关标记）。
"""

class Selectors:
    # ==========================================
    # 1. 登录与基础信息提取 (Login & User Info)
    # ==========================================
    LOGIN = {
        # 二维码元素
        "QR_CODE": [".qr-code", "[class*='qr']", "[class*='QRCode']", "canvas[class*='qr']", ".login-qrcode"],
        # 用户名/手机号输入框
        "USERNAME_INPUT": ["input[type='text']", "input[name*='user']", "input[placeholder*='手机']", "input[placeholder*='账号']"],
        # 密码输入框
        "PASSWORD_INPUT": ["input[type='password']"],
        # 登录按钮
        "LOGIN_BTN": ["button[type='submit']", "[class*='login-btn']", "button:has-text('登录')"],
    }
    
    USER_INFO = {
        # 用户昵称提取
        "NICKNAME": [
            ".user-info .nickname", 
            "[class*='user-name']", 
            "[class*='userName']", 
            ".user-info .name", 
            ".header-user-name", 
            ".semi-avatar-label",
            ".name-_lSSDc",
            "div.name-_lSSDc"
        ],
        # 用户头像提取
        "AVATAR": [
            "[class*='avatar']", 
            "img[class*='avatar']", 
            ".user-avatar img", 
            ".semi-avatar img"
        ]
    }
    
    # 登录检测关键 Cookie Name
    REQUIRED_COOKIES = ['sessionid', 'sessionid_ss']


    # ==========================================
    # 2. 首页入口与发布导航（唯一匹配，便于步骤失败时快速定位）
    # ==========================================
    HOME = {
        # OpenClaw《抖音_图文发布DOM分析报告》：首页顶部「高清发布」进入发布域，默认打开图文发布页；
        # 视频需在发布页 Tab 栏切换到「视频」（见 PUBLISH.TAB_VIDEO）。与左侧卡片「发布视频」并存时优先尝试卡片。
        "PUBLISH_HD_ENTRY_BTN": [
            "button:has-text('高清发布')",
            "button.douyin-creator-master-button-primary:has-text('高清发布')",
            "[class*='douyin-creator-master-button']:has-text('高清发布')",
            "[class*='header-button']:has-text('高清发布')",
            "[ref=e13]",
        ],
        # 步骤2：发布视频入口按钮（优先文案/角色选择器，哈希类末尾兜底；抖音改版后哈希类会失效）
        # 注：抖音首页已有「高清发布」统一入口，进入后在 Tab 切换到视频；
        # 若「发布视频」卡片不存在则自动回退到 PUBLISH_HD_ENTRY_BTN + TAB_VIDEO（见 step_02_entry.py）
        "PUBLISH_VIDEO_BTN": [
            "button:has-text('发布视频')",
            "div[role='button']:has-text('发布视频')",
            "a:has-text('发布视频')",
            "span:has-text('发布视频')",
            "[class*='video']:has-text('发布视频')",
            "[class*='btn']:has-text('发布视频')",
            # 旧版哈希类（页面改版后可能失效，放末尾兜底）
            "div.btn-OkpBsP.video-_cFVs8",
            "div[class*='btn'][class*='video']",
        ],
        # 步骤2：发布图文入口按钮（优先文案/角色选择器，哈希类末尾兜底）
        "PUBLISH_IMAGE_BTN": [
            "button:has-text('发布图文')",
            "div[role='button']:has-text('发布图文')",
            "a:has-text('发布图文')",
            "span:has-text('发布图文')",
            "[class*='image']:has-text('发布图文')",
            "[class*='btn']:has-text('发布图文')",
            # 旧版哈希类（页面改版后可能失效，放末尾兜底）
            "div.btn-OkpBsP.image-k7R89r",
            "div[class*='btn'][class*='image']",
        ],
        # 进入视频/图文发布页后的特征元素（用于步骤2 校验）
        # 使用更贴近“视频/图文差异”的特征：优先 title placeholder，其次按 accept 区分文件 input
        "VIDEO_PUBLISH_PAGE_MARKERS": [
            # 文案/accept 改版时优先用模糊 placeholder、上传按钮与拖拽区 file（与步骤3 FILE_INPUT 一致）
            "input[placeholder*='填写作品标题']",
            "input[placeholder='填写作品标题，为作品获得更多流量']",
            "button:has-text('上传视频')",
            "div.container-drag-VAfIfu input[type='file'][accept*='video']",
            "div.container-drag-VAfIfu input[type='file']",
        ],
        "IMAGE_PUBLISH_PAGE_MARKERS": [
            "input[placeholder*='添加作品标题']",
            "input[placeholder='添加作品标题']",
            "button:has-text('上传图文')",
            "div.container-drag-VAfIfu input[type='file'][accept*='image']",
        ],
    }


    # ==========================================
    # 3. 视频/图文内容发布（唯一匹配，DOM 见 docs/03插件系统/01抖音插件/3.1.4抖音插件DOM对照表.md）
    # ==========================================
    PUBLISH = {
        "CONTENT_TYPE_TABS": ["div[role='tablist'] button:has-text('视频')"],
        "TAB_VIDEO": ["div[role='tablist'] button:has-text('视频')"],
        "TAB_IMAGE": ["div[role='tablist'] button:has-text('图文')"],
        # 步骤3 唯一匹配：<button class="semi-button semi-button-primary container-drag-btn-k6XmB4">上传视频
        "UPLOAD_BTN": [
            "button:has-text('上传视频')",
            "button.container-drag-btn-k6XmB4",
        ],
        "UPLOAD_IMAGE_BTN": [
            "button:has-text('上传图文')",
            "button.container-drag-btn-k6XmB4",
        ],
        # 步骤3 唯一匹配：div.container-drag-VAfIfu 内 input
        "FILE_INPUT": ["div.container-drag-VAfIfu input[type='file']"],
        "IMAGE_FILE_INPUT": ["div.container-drag-VAfIfu input[type='file'][accept*='image']"],
        # 步骤3 视频上传成功判定：出现「重新上传」区域即表示视频已上传（唯一匹配 DOM）
        # <label class="upload-btn-PdfuUv"> 内含 input[accept*='video'] + 上传图标按钮，文案「重新上传」
        # OpenClaw DOM 报告中重传按钮：`[ref=e522]`（ref 属性为会话内临时值，排列在稳定选择器之后作为备选）
        "VIDEO_UPLOAD_SUCCESS_MARKER": ["label.upload-btn-PdfuUv", "[ref=e522]"],
        "REUPLOAD_BTN": ["label.upload-btn-PdfuUv", "[ref=e522]"],
        "IMAGE_THUMBNAIL": ["div.container-drag-VAfIfu div[class*='thumb'] img"],
        # 图文上传成功：预览区出现「清空并重新上传」（span.semi-button-content 内含云上传图标+文案）
        "IMAGE_UPLOAD_SUCCESS_MARKER": [
            # OpenClaw DOM 报告中图文成功标记：
            # - 出现「已添加N张图片」
            # - 同时出现「继续添加」按钮
            "button:has-text('继续添加')",
            "text=\"已添加\"",
            "#DCPF div.bottom-button-C8U8y7 button span.semi-button-content:has-text('清空并重新上传')",
            "div.bottom-button-C8U8y7 span.semi-button-content:has-text('清空并重新上传')",
            "#DCPF div.content-right-ik9gts span.semi-button-content:has-text('清空并重新上传')",
            "#DCPF button:has(span.semi-button-content:has-text('清空并重新上传'))",
            "span.semi-button-content:has-text('清空并重新上传')",
            "[ref=e284]",  # 会话内 ref，仅作最后备选
        ],
        "UPLOAD_SUCCESS_TEXT": "text=\"上传成功\"",
        # 步骤4 标题：视频发布页 placeholder 与图文不同；图文为「添加作品标题」
        "TITLE_INPUT": [
            # 稳定选择器优先，ref 属性仅作最后备选（会话内临时值，页面重载后可能失效）
            "input[placeholder='填写作品标题，为作品获得更多流量']",
            "#DCPF div.content-left-F3wKrk input.semi-input[placeholder='添加作品标题']",
            "input.semi-input.semi-input-default[placeholder='添加作品标题']",
            "input[placeholder='添加作品标题']",
            "[ref=e212]",  # 视频标题 ref，仅作最后备选
            "[ref=e166]",  # 图文标题 ref，仅作最后备选
        ],
        # 步骤4 描述区：视频为 data-placeholder「添加作品简介」；图文为 editor-comp-publish +「添加作品描述...」
        "DESC_EDITOR": [
            # 强化版的首选编辑器选择器：优先查找带有 .editor-comp-publish 类的真实可交互编辑器，避免命中被隐藏但 `is_visible` 误判的旧节点导致超时
            "div.zone-container.editor-kit-container.editor.editor-comp-publish[contenteditable='true']",
            # 稳定选择器优先，ref 仅作最后备选
            "div.zone-container.editor-kit-container.editor[data-placeholder='添加作品简介'][contenteditable='true']",
            "div[data-placeholder='添加作品描述...'][contenteditable='true']",
            "#DCPF div.content-left-F3wKrk div.editor-kit-editor-container.old div.zone-container.editor-kit-container.editor[contenteditable='true']",
            "div.editor-kit-editor-container.old div.zone-container.editor-kit-container.editor[contenteditable='true']",
            "[ref=e217]",  # 视频描述 ref，仅作最后备选
            "[ref=e174]",  # 图文描述 ref，仅作最后备选
        ],
        "DESC_PLACEHOLDER": [
            "div[data-placeholder='添加作品简介']",
            "div[data-placeholder='添加作品描述...']",
        ],
        "TOPIC_INPUT": ["input[placeholder*='话题']"],
        "AT_LIST_CONTAINER": [".at-list-container"],
        # 步骤5：竖封面「选择封面」入口（视频页）
        # 注意：部分账号「设置封面」在「作品描述」上方，部分在下方；不得依赖全页 .first 或 nth-child(2)。
        # 步骤内优先在 div.cover-Jg3T4p 内查找同时含「竖封面」+「选择封面」的单元格，再回退到下列候选。
        # 真实 DOM：<div class="filter-k_CjvJ">…<div class="title-wA45Xd">选择封面</div>…竖封面 3:4
        "COVER_BTN": [
            # DOM 报告 Layer 2：竖封面3:4「选择封面」
            "[ref=e165]",
            # 封面区第一个子节点即竖封面 3:4（覆盖 filter- class 有无的情况）
            "div.cover-Jg3T4p > div.filter-k_CjvJ:first-child",
            "div.cover-Jg3T4p > div:first-child",
        ],
        # 步骤5 唯一匹配：封面弹窗容器
        # 步骤5 封面弹窗容器（DOM 报告稳定选择器）
        "COVER_MODAL": ["div.dy-creator-content-modal-content"],
        "COVER_THUMB": ["div.dy-creator-content-modal-content img"],
        # 步骤5 弹窗内「设置横封面」按钮（3.1.3 D 步真实 DOM）
        # 改版后可能为 Tab/伪按钮结构，补充 text 引擎与模糊 class 兜底
        "COVER_HORIZONTAL_BTN": [
            "span.semi-button-content:has-text('设置横封面')",
            "button:has-text('设置横封面')",
            "div[role='tab']:has-text('设置横封面')",
            "div[role='tab']:has-text('横封面')",
            "[class*='tab']:has-text('设置横封面')",
            "[class*='tab-btn']:has-text('横')",
            "span:has-text('设置横封面')",
            "text=/设置\\s*横封面/",
            "text=/去设置.*横/",
        ],
        # 步骤5 有几率出现的「设置竖封面获更多流量」推荐弹窗：弹窗容器（class 含 verticalSupportDualCoverModal）
        "COVER_VERTICAL_PROMO_MODAL": ["div.dy-creator-content-modal-content[class*='verticalSupportDualCoverModal']", "div[role='dialog']:has-text('设置竖封面获更多流量')"],
        # 步骤5 上述推荐弹窗内的「设置竖封面」按钮（红底，点击后进入竖封面设置）
        "COVER_VERTICAL_PROMO_BTN": [
            "div.dy-creator-content-modal-content[class*='verticalSupportDualCoverModal'] >> span.semi-button-content:has-text('设置竖封面')",
            "div[role='dialog']:has-text('设置竖封面获更多流量') >> button:has-text('设置竖封面')",
            "div[role='dialog']:has-text('设置竖封面获更多流量') >> span.semi-button-content:has-text('设置竖封面')",
        ],
        # 步骤5 唯一匹配：设置竖封面页面的「完成」按钮
        # 真实 DOM：<button class="semi-button semi-button-primary semi-button-light primary-RstHX_"><span class="semi-button-content">完成</span></button>
        # 步骤5 弹窗内「完成」按钮（点击后触发封面检测，见 3.1.3 D 步真实 DOM）
        "COVER_CONFIRM_BTN": [
            "span.semi-button-content:has-text('完成')",
            "button:has-text('完成')",
        ],
        # 步骤5 唯一匹配：弹窗内上传区域
        "COVER_UPLOAD_BTN": ["div.semi-upload-drag-area"],
        "COVER_FILE_INPUT": ["input.semi-upload-hidden-input[type='file']"],
        # 步骤5 AI 方向唯一匹配：红框内第一个缩略图（视频页面主区域，不进弹窗）
        "COVER_AI_RECOMMEND_FIRST": ["div:has-text('AI智能推荐封面') >> img"],
        # 步骤5 图文封面弹窗内「AI智能封面」选项卡入口（图文发布页弹窗专用）
        "COVER_AI_OPTION": [
            "div.dy-creator-content-modal-content span:has-text('AI智能封面')",
            "div.dy-creator-content-modal-content [class*='tab']:has-text('AI智能封面')",
            "div.dy-creator-content-modal-content button:has-text('AI智能封面')",
        ],
        # 步骤5 完成标准：页面出现「封面效果检测通过」或「封面检测通过」即视为封面设置成功
        # 真实 DOM：<div class="container-QVu5RH success-container-vgr8T8 coverChecking-fmip_6"> 内含 <span>封面效果检测通过</span>
        # 或发文助手区域：<div class="title-owSXGj">封面检测通过</div>
        "COVER_SUCCESS_INDICATOR": [
            "div.container-QVu5RH.success-container-vgr8T8.coverChecking-fmip_6",
            "span:has-text('封面效果检测通过')",
            "div.title-owSXGj:has-text('封面检测通过')",
            "div.suggest-uyKWlF:has(div.title-owSXGj:has-text('封面检测通过'))",
        ],
        # 步骤5 封面缺失提示：「横/竖双封面缺失」表示横封面和竖封面都未设置
        # 真实 DOM：<div class="title-owSXGj" style="color: rgb(246, 152, 41);">横/竖双封面缺失</div>
        "COVER_MISSING_INDICATOR": [
            "div.title-owSXGj:has-text('横/竖双封面缺失')",
            "div.suggest-uyKWlF:has(div.title-owSXGj:has-text('横/竖双封面缺失'))",
        ],
        # 步骤6 图文：扩展信息「选择音乐」/ 选完后「修改音乐」
        # OpenClaw 20260405：入口为 role=button（报告 e411/e414）；旧版为 span.action-Q1y01k，两套都保留
        # 2026-04 实测 /content/post/image：左侧为字段名「选择音乐」，灰色条右侧铅笔旁才是可点入口（勿点整条灰条）。
        # 优先 container-right + span.action；通用 button 可能点到错误节点，放后。
        "MUSIC_ENTRY_SELECT": [
            "#DCPF div.content-left-F3wKrk div.container-right-uW7Pj1 span.action-Q1y01k:has-text('选择音乐')",
            "#DCPF div.content-left-F3wKrk div[class*='container-right'] span[class*='action']:has-text('选择音乐')",
            "div.container-right-uW7Pj1 span.action-Q1y01k:has-text('选择音乐')",
            "div[class*='container-right'] span[class*='action']:has-text('选择音乐')",
            "span.action-Q1y01k:has-text('选择音乐')",
            "#DCPF button:has-text('选择音乐')",
            "button:has-text('选择音乐')",
            "div[role='button']:has-text('选择音乐')",
            "[ref=e326]",  # 音乐入口 ref，仅作最后备选
        ],
        "MUSIC_ENTRY_MODIFY": [
            "#DCPF button:has-text('修改音乐')",
            "button:has-text('修改音乐')",
            "div[role='button']:has-text('修改音乐')",
            "#DCPF div.content-left-F3wKrk div.container-right-uW7Pj1 span.action-Q1y01k:has-text('修改音乐')",
            "#DCPF div.content-left-F3wKrk div[class*='container-right'] span[class*='action']:has-text('修改音乐')",
            "div.container-right-uW7Pj1 span.action-Q1y01k:has-text('修改音乐')",
            "div[class*='container-right'] span[class*='action']:has-text('修改音乐')",
            "span.action-Q1y01k:has-text('修改音乐')",
            "[ref=e326]",  # 同上，修改音乐 ref 备选
        ],
        # 音乐抽屉内搜索框（用于填关键字等；「抽屉是否已打开」判定见 step_06a_music._is_music_panel_open，勿用 type=search 等宽泛项）
        "MUSIC_PANEL_SEARCH_INPUT": [
            "input[placeholder='搜索音乐']",
            'input[placeholder*="搜索音乐"]',
            "[ref=e638]",  # 20260405 报告搜索框 ref
            "[ref=e549]",  # 旧报告 ref，备用
            "[ref=e962]",
        ],
        # 「使用」按钮（DOM 报告 20260405：点击音乐条目后动态出现在条目内部右侧，ref=e1022）
        # 注意：触发方式是「点击条目」而非 hover，按钮出现在被点击的条目 div[role=button] 内部
        "MUSIC_USE_BTN": [
            "button:has-text('使用')",
            "div[role='button']:has-text('使用')",
            "span:has-text('使用')",
            "[ref=e1022]",  # 20260405 报告使用按钮 ref
            "[ref=e929]",   # 旧报告 ref，备用
            "[ref=e1106]",
        ],
        # 步骤6 音乐面板分类标签页（推荐/热门榜/收藏/飙升榜/原创榜/卡点/纯音乐/旅行/DJ/搞笑/流行/伤感）
        # DOM 报告 20260405：标签页 role='tab'，ref=e648（推荐）/e649（热门榜）/e650（收藏）
        "MUSIC_PANEL_TABS": [
            "[role='tab']",
            "div[role='tablist'] [role='tab']",
        ],
        # 步骤6 音乐面板：已选后显示的音乐名称区域（DOM 报告 20260405：ref=e406/e407）
        "MUSIC_SELECTED_NAME": [
            "[ref=e406]",   # 20260405 报告已选音乐显示区 ref
            "[ref=e407]",
            "[ref=e939]",   # 旧报告 ref，备用
            "[ref=e1343]",
        ],
        # 步骤6 音乐面板：已选后显示的音乐时长区域（DOM 报告 20260405：ref=e1032）
        "MUSIC_SELECTED_DURATION": [
            "[ref=e1032]",  # 20260405 报告已选音乐时长 ref
            "[ref=e940]",
            "[ref=e1344]",
        ],
        # 步骤6 音乐面板关闭按钮（DOM 报告 20260405：ref=e627）
        "MUSIC_PANEL_CLOSE_BTN": [
            "[ref=e627]",   # 20260405 报告关闭按钮 ref
            "[ref=e538]",
            "[ref=e951]",
        ],
        # 步骤6 视频扩展信息「添加标签」行（OpenClaw 抖音_视频发布DOM分析报告 §3.3）
        # 结构：类型下拉（位置/团购/购物车/小程序）→ 打卡|带货 下拉（选「位置」时出现）→ 主输入框
        "EXTRA_ADD_TAG_LOCATION_INPUT": [
            "input[placeholder='输入地理位置']",
            "input[placeholder*='地理位置']",
            "[ref=e349]",
        ],
        # 购物车：OpenClaw《抖音创作者中心视频发布页面购物车添加功能的DOM结构分析及操作流程验证》
        "EXTRA_CART_LINK_INPUT": [
            'input[placeholder="粘贴商品链接"]',
            "input[placeholder='粘贴商品链接']",
            "input[placeholder*='粘贴商品链接']",
        ],
        # 「添加链接」为 SPAN，非 button；class 含哈希 cart-mybtn-*
        "EXTRA_CART_ADD_LINK_SPAN": [
            "span.cart-mybtn-jPFx5X",
            "span[class*='cart-mybtn']",
        ],
        # 标签类型下拉（原「位置」入口，选购物车）；class 含 select-* 哈希
        "EXTRA_TAG_TYPE_SEMI_SELECT": [
            "div.semi-select.select-lJTtRL.semi-select-single",
            "div.semi-select[class*='select-'].semi-select-single",
        ],
        # 购物车锚点区域（含链接输入 + 添加链接）
        "EXTRA_CART_ANCHOR_WRAP": [
            "div.anchor-component-Shp3mT",
            "div[class*='anchor-component']",
        ],
        # Semi 下拉选项层（挂载在 body，全页共用）
        "SEMI_SELECT_OPTION": [
            "div.semi-select-option",
            "[role='option']",
            "div[role='option']",
        ],
        # 步骤8：发布按钮（L1 role/name=发布 由代码直接调用 get_by_role；L2 文案匹配；L3 哈希 class 易碎置后）
        # 说明：哈希类（primary-cECiOJ、button-dhlUZE 等）随版本变更会失效，优先用语义选择器
        "SUBMIT_BTN": [
            # Semi UI 主按钮：type=submit 或带 primary class
            "button[type='submit']:has-text('发布')",
            "button.semi-button-primary:has-text('发布')",
            "button.semi-button.semi-button-primary:has-text('发布')",
            # 底部固定发布区（fixed/sticky 定位，优先于普通位置）
            "div[class*='fixed'] button:has-text('发布')",
            "div[class*='bottom'] button.semi-button-primary:has-text('发布')",
            # 通用文案兜底
            "button:has-text('发布')",
            # 旧版哈希类（可能失效）
            "button[class*='primary-cECiOJ']:has-text('发布')",
            "button[class*='button-dhlUZE'][class*='primary']:has-text('发布')",
            "button.button-dhlUZE.primary-cECiOJ.fixed-J9O8Yw:has-text('发布')",
            "[ref=e476]",  # 视频页 ref，会话内可能变化
            "[ref=e445]",  # 图文页 ref
        ],
    }


    # ==========================================
    # 4. 风控及异常（唯一匹配，步骤1/8 用）
    # ==========================================
    SECURITY = {
        # 步骤1 唯一匹配：风控/账号异常弹窗
        "RISK_MODAL": ["div[role='dialog']:has-text('账号异常')"],
        "PUBLISH_TOAST_ERROR": [".semi-toast:has-text('失败')"],
        "PUBLISH_TOAST_FREQ": [".semi-toast:has-text('频繁')"],
        "PUBLISH_MODAL_COVER": [".semi-modal:has-text('封面')"],
        "PUBLISH_MODAL_SUPPLEMENT": ["div[role='dialog']:has-text('补充信息')"],
    }

    # ==========================================
    # 5. 发布结果验证（唯一匹配）
    # ==========================================
    VERIFY = {
        # 作品管理页特征元素（发布成功后跳转落地的作品列表/数据页）
        "MANAGE_PAGE_INDICATOR": [
            "div:has-text('作品数据')",
            "div:has-text('视频管理')",
            "div:has-text('图文管理')",
        ],
        # OpenClaw 视频报告 §8.2：跳转后可用「作品管理」文案辅助判定
        "MANAGE_PAGE_TITLE": [
            "text=作品管理",
            "div:has-text('作品管理')",
        ],
        # 步骤8 发布成功 Toast（多候选兜底，Toast 消失极快需尽快捕获）
        # 优先精确类名选择器，再退到文案匹配
        "SUCCESS_TOAST": "span.semi-toast-content-text:has-text('发布成功')",
        "SUCCESS_TOAST_ALT": [
            ".semi-toast-success span:has-text('发布成功')",
            ".semi-toast:has-text('发布成功')",
            "div[class*='toast']:has-text('发布成功')",
            "text='发布成功'",
        ],
    }

    # ==========================================
    # 6. 发布设置（步骤7，唯一匹配 DOM 见对照表）
    # ==========================================
    SETTINGS = {
        # 谁可以看：<label class="radio-d4zkru"> 内 <input class="radio-native-p6VBGt" value=0/2/1>
        # 与「立即发布」相同：label 在 flex 下 bbox 可能过宽，human_click 点在 label 上易误选相邻项（如设公开却点到好友可见）。
        # 必须优先勾选 label 内的 native input，与 3.1.4 DOM 对照表一致。
        # OpenClaw：视频 公开 e424 / 好友 e426 / 私密 e428；图文 公开 e406 / 好友 e408 / 私密 e410
        "PRIVACY_PUBLIC": [
            "label.radio-d4zkru:has-text('公开') input.radio-native-p6VBGt",
            "label.radio-d4zkru:has-text('公开')",
            "[ref=e424]",
            "[ref=e406]",
        ],
        "PRIVACY_FRIEND": [
            "label.radio-d4zkru:has-text('好友可见') input.radio-native-p6VBGt",
            "label.radio-d4zkru:has-text('好友可见')",
            "[ref=e426]",
            "[ref=e408]",
        ],
        "PRIVACY_PRIVATE": [
            "label.radio-d4zkru:has-text('仅自己可见') input.radio-native-p6VBGt",
            "label.radio-d4zkru:has-text('仅自己可见')",
            "[ref=e428]",
            "[ref=e410]",
        ],
        "SAVE_ALLOW": [
            "label.radio-d4zkru:has-text('允许') input.radio-native-p6VBGt",
            "label.radio-d4zkru:has-text('允许')",
            "[ref=e441]",
            "[ref=e423]",
        ],
        "SAVE_DISALLOW": [
            "label.radio-d4zkru:has-text('不允许') input.radio-native-p6VBGt",
            "label.radio-d4zkru:has-text('不允许')",
            "[ref=e443]",
            "[ref=e425]",
        ],
        # 立即发布：
        #   视频页：label.radio-d4zkru > input.radio-native-p6VBGt（radio 结构）
        #   图文页：checkbox 结构，label 内 input[type='checkbox']（OpenClaw 图文报告 §9.4 e435）
        # 必须优先点 native input，避免点在过宽 label 上误选相邻项。
        "PUBLISH_NOW": [
            # 视频页 radio
            "label.radio-d4zkru.one-line-pe7juM:has-text('立即发布') input.radio-native-p6VBGt",
            "label.radio-d4zkru:has-text('立即发布') input.radio-native-p6VBGt",
            # 图文页 checkbox：先找 label 内 input，再退到 label
            "label:has-text('立即发布') input[type='checkbox']",
            "label:has-text('立即发布') input",
            "label:has-text('立即发布')",
            "[ref=e456]",  # 视频页 ref
            "[ref=e435]",  # 图文页 ref
        ],
        # 定时发布：
        #   视频页：label.radio-d4zkru > input.radio-native-p6VBGt（radio 结构）
        #   图文页：checkbox 结构，label 内 input[type='checkbox']（OpenClaw 图文报告 §9.4 e437）
        "PUBLISH_SCHEDULE": [
            # 视频页 radio
            "label.radio-d4zkru.one-line-pe7juM:has-text('定时发布') input.radio-native-p6VBGt",
            "label.radio-d4zkru:has-text('定时发布') input.radio-native-p6VBGt",
            # 图文页 checkbox：先找 label 内 input，再退到 label
            "label:has-text('定时发布') input[type='checkbox']",
            "label:has-text('定时发布') input",
            "label:has-text('定时发布')",
            "[ref=e458]",  # 视频页 ref
            "[ref=e437]",  # 图文页 ref
        ],
        "SCHEDULE_INPUT": ["input[format='yyyy-MM-dd HH:mm']", "[ref=e463]", "[ref=e1472]"],
    }

    # ==========================================
    # 7. 步骤级补充选择器（原步骤内硬编码，统一收归此处）
    # ==========================================
    STEP_EXTRAS = {
        # step_02_entry.py：确认已进入发布页的标记
        "ENTRY_VIDEO_TITLE_PLACEHOLDER": "input[placeholder='填写作品标题，为作品获得更多流量']",
        "ENTRY_IMAGE_TITLE_PLACEHOLDER": "input[placeholder='添加作品标题']",
        # step_05_cover_video.py：封面区域标记
        "COVER_AREA_MARKER": ["div.cover-Jg3T4p", "text=设置封面"],
        "COVER_AREA_PANEL": ["#DCPF div.cover-Jg3T4p", "div.cover-Jg3T4p"],
        # step_06a_music.py：搜索框回退备选（与 MUSIC_PANEL_SEARCH_INPUT 兼容）
        "MUSIC_SEARCH_INPUT_TYPE": "input[type='search']",
        # step_08_submit.py：发布成功 Toast 备用选择器
        "TOAST_SUCCESS_ALT": [
            ".semi-toast-success:has-text('发布成功')",
            "text='发布成功'",
        ],
        # step_07_settings.py：定时发布时间输入备选（日期选择器降级）
        "SCHEDULE_DATE_PICKER_ALT": [
            ".semi-datepicker-input input",
            "input.semi-input[placeholder='日期和时间']",
            "input[placeholder*='日期和时间']",
            "input[placeholder*='发布时间']",
            "input[class*='date-picker']",
        ],
    }
