# 快手创作者中心 - 视频发布页面 DOM 对照表

> 页面URL: `https://cp.kuaishou.com/article/publish/video`
> 分析日期: 2026-03-09
> 技术栈: React + Ant Design (antd)
> 说明: 本文档详细记录快手视频发布页面所有可交互元素的 DOM 信息，供自动化脚本/AI编程参考。

> **实现约定**：关键按钮（如定时弹窗「确定」）在代码中须用真实鼠标或 Locator 点击，见 [3.2 第 5.2 节](../3.2插件选择器标准化规范.md)。

---

## 一、页面整体结构

### 1.1 顶层容器

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 页面根容器 | `#app` → `.complete` → `.haploid-body` | 快手使用 haploid 微前端框架 |
| 编辑区域（左侧） | `._edit-section_ql0z6_20` | 包含表单和预览两个子div |
| 表单区域 | `._edit-section-form_ql0z6_100` | 包含所有表单项（7个子元素） |
| 预览+助手区域（右侧） | `._edit-section_ql0z6_20 > div:nth-child(2)` | 包含 `<main>` 预览区 和 `._helper_1kfmm_1` 创作助手 |
| 底部按钮区域 | `._edit-section-btns_ql0z6_118` | 包含"发布"和"取消"按钮 |

### 1.2 左侧导航菜单

| 菜单项 | CSS 选择器 | role 属性 |
|--------|----------|----------|
| 首页 | `[role="menuitem"]` 文本="首页" | menuitem |
| 内容管理 | `[role="menuitem"]` 文本="内容管理" | menuitem |
| 互动管理 | `[role="menuitem"]` 文本="互动管理" | menuitem |
| 数据中心 | `[role="menuitem"]` 文本="数据中心" | menuitem |
| 成长中心 | `[role="menuitem"]` 文本="成长中心" | menuitem |
| 创作服务 | `[role="menuitem"]` 文本="创作服务" | menuitem |
| 其他服务 | `[role="menuitem"]` 文本="其他服务" | menuitem |

---

## 二、作品描述区域

### 2.1 描述输入框（contenteditable）

| 属性 | 值 |
|------|-----|
| **CSS选择器** | `._description_17g9x_24` |
| **标签** | `<div>` |
| **contenteditable** | `true` |
| **父容器** | `._edit-desc-container_17g9x_7` |
| **占位文本** | "作品描述不多写一句？试试智能文案" (通过伪元素/placeholder类显示) |

**自动化操作方式:**
```javascript
// 填写描述文本
const desc = document.querySelector('._description_17g9x_24');
desc.focus();
desc.innerHTML = '你的作品描述文字 #话题标签';
desc.dispatchEvent(new Event('input', { bubbles: true }));
```

### 2.2 AI 智能按钮组

| 按钮 | CSS 选择器 | 功能说明 |
|------|----------|---------|
| 按钮容器 | `._ai-buttons_1gvw3_13` | 包含三个AI按钮 |
| 智能文案 | `._ai-button_1gvw3_13:nth-child(1)` | 自动生成文案 |
| 智能话题 | `._ai-button_1gvw3_13:nth-child(2)` | 自动推荐话题标签 |
| 好友(@) | `._ai-button_1gvw3_13:nth-child(3)` | @好友功能 |
| 按钮图标 | `._ai-button-icon_1gvw3_30` (文案) / `._ai-button-icon-topic_1gvw3_37` (话题) / `._ai-button-icon-friend_1gvw3_45` (好友) | 各按钮的图标 |
| 按钮文字 | `._ai-button-text_1gvw3_53` | 按钮文字元素 |
| 创作助手入口 | 橙色按钮 "创作助手帮你做运营!" | 浮动在AI按钮右侧 |

### 2.3 推荐话题标签

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 推荐区域容器 | `._ai-topics_1gvw3_124` | 话题推荐整体容器 |
| "推荐:" 标题 | `._ai-topics-title_1gvw3_131` | |
| 话题列表容器 | `._ai-topics-items_1gvw3_170` | |
| 单个话题项 | `._ai-topics-item_1gvw3_170` | 例: "#记录维修中点点滴滴" |
| "全部" 按钮 | `._ai-topics-all_1gvw3_205` | 展开查看更多话题 |

**自动化操作方式:**
```javascript
// 点击推荐话题添加到描述
document.querySelector('._ai-topics-item_1gvw3_170').click();
```

---

## 三、活动推荐区域

| 属性 | CSS 选择器 | 说明 |
|------|----------|------|
| 标签label | `._label_1quq7_19` (文本="活动推荐") | 所属表单项: `._edit-form-item_1quq7_7` |
| 活动项容器 | `._activity__item_3v4ib_1` | 每个活动为一个item |
| 活动标题 | `._activity__item_main_title_3v4ib_56` | 例: "助农帮帮团春耕预热活动" |
| 操作区域 | `._activity__item_main_opera_3v4ib_66` | |
| "去领取" 按钮 | `._activity__item_main_opera_detail_3v4ib_85` | 点击领取活动 |

---

## 四、封面设置区域

### 4.1 封面编辑器

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 封面编辑器容器 | `._high-cover-editor_ps02t_1` | 整个封面设置区域 |
| 封面标签 | `._high-cover-editor-label_ps02t_8` (文本="封面设置") | |
| 封面主区域 | `._high-cover-editor-main_ps02t_16` | |
| 默认封面(大图) | `._default-cover_ps02t_86._big_ps02t_95` | 当前选中的封面 |
| 封面编辑按钮 | `._cover-full-editor_ps02t_40` (文本="封面设置") | 点击进入封面编辑 |
| 封面图片 | `._default-cover_ps02t_86 img` | src为blob URL |

### 4.2 智能推荐封面

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 推荐封面容器 | `._recommend-cover_ps02t_149` | |
| 推荐封面标题 | `._recommend-cover-header_ps02t_162` (文本="智能推荐封面") | |
| 推荐封面列表 | `._recommend-cover-main_ps02t_168` | |
| 单个推荐封面 | `._recommend-cover-item_ps02t_176` | 点击可选择 |
| 封面遮罩层 | `._masks-wrapper_ps02t_186` / `._masks_ps02t_186` | |

### 4.3 PK封面开关

| 属性 | 值 |
|------|-----|
| **CSS选择器** | `._high-cover-editor_ps02t_1 .ant-switch.ant-switch-small` |
| **标签文本** | `._label_ps02t_450` (文本="PK封面") |
| **当前状态** | `aria-checked="false"` (关闭) |
| **判断开启** | 检查类名是否包含 `ant-switch-checked` |

**自动化操作方式:**
```javascript
// 开启PK封面
const pkSwitch = document.querySelector('._high-cover-editor_ps02t_1 .ant-switch');
if (!pkSwitch.classList.contains('ant-switch-checked')) {
    pkSwitch.click();
}
```

---

## 五、作者服务区域

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 表单项容器 | `._edit-form-item_1quq7_7._author-turning-item_1quq7_12` | |
| 标签 | `._label_1quq7_19` (文本="作者服务") | |
| 服务类型选择器 | `.ant-select` (id=`rc_select_4`) | placeholder="选择服务类型" |
| 关联收益选择器 | `.ant-select` (id=`rc_select_5`) | placeholder="关联成功可获得更多收益"，默认disabled |

**自动化操作方式:**
```javascript
// 选择作者服务类型
const serviceSelect = document.querySelector('#rc_select_4');
serviceSelect.focus();
serviceSelect.value = ''; // 先清空
// 模拟输入以触发下拉
const inputEvent = new Event('change', { bubbles: true });
serviceSelect.dispatchEvent(inputEvent);
```

---

## 六、关联热点

| 属性 | 值 |
|------|-----|
| **表单项容器** | `._edit-form-item_1quq7_7` (label="关联热点") |
| **标签** | `._label_1quq7_19` (文本="关联热点") |
| **选择器组件** | `.ant-select` |
| **输入框ID** | `rc_select_0` |
| **placeholder** | "输入你想关联的热点" |
| **组件类型** | `ant-select-show-search` (可搜索下拉) |

**自动化操作方式:**
```javascript
// 搜索并选择热点
const hotInput = document.querySelector('#rc_select_0');
hotInput.focus();
hotInput.value = '关键词';
hotInput.dispatchEvent(new Event('input', { bubbles: true }));
// 等待下拉出现后点击选项
```

---

## 七、作者声明

| 属性 | 值 |
|------|-----|
| **表单项容器** | `._edit-form-item_1quq7_7` (label="作者声明") |
| **标签** | `._label_1quq7_19` (文本="作者声明") |
| **选择器组件** | `.ant-select` |
| **输入框ID** | `rc_select_1` |
| **placeholder** | "为作品添加补充说明" |

---

## 八、添加地点

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 表单项容器 | `._edit-form-item_1quq7_7` (label="添加地点") | |
| 地区级联选择器 | `.ant-select.ant-cascader` (id=`rc_select_2`) | placeholder="请选择所在地区", 宽度168px |
| 详细地址输入框 | `.ant-select` (id=`rc_select_3`) | placeholder="请输入视频详细地址，让同城老铁看见你", 默认disabled (需先选择地区) |

**自动化操作方式:**
```javascript
// 先选择地区
const regionSelect = document.querySelector('#rc_select_2');
regionSelect.focus();
// 等待级联菜单出现，逐级选择
// 选择地区后，详细地址输入框会自动启用
```

---

## 九、发布设置区域

### 9.1 互动设置（Checkbox 多选）

| 选项 | CSS 选择器 | input value | 默认状态 |
|------|----------|------------|---------|
| 允许别人跟我拍同框 | `.ant-checkbox-wrapper` (value=`allowSameFrame`) | `allowSameFrame` | 已勾选 ✅ |
| 允许下载此作品 | `.ant-checkbox-wrapper` (value=`downloadType`) | `downloadType` | 已勾选 ✅ |
| 作品展示在同城页 | `.ant-checkbox-wrapper` (value=`disableNearbyShow`) | `disableNearbyShow` | 已勾选 ✅ |

**容器:** `.ant-checkbox-group`
**表单标签:** `._label_1quq7_19` (文本="互动设置")

**自动化操作方式:**
```javascript
// 取消勾选"允许下载此作品"
const downloadCheckbox = document.querySelector('.ant-checkbox-input[value="downloadType"]');
if (downloadCheckbox.checked) {
    downloadCheckbox.click(); // 或点击父级 .ant-checkbox-wrapper
}
```

**判断状态:**
```javascript
// 判断checkbox是否勾选
const wrapper = document.querySelector('.ant-checkbox-wrapper');  // 选具体的
const isChecked = wrapper.classList.contains('ant-checkbox-wrapper-checked');
```

### 9.2 查看权限（Radio 单选）

| 选项 | CSS 选择器 | input value | 默认状态 |
|------|----------|------------|---------|
| 所有人可见 | `.ant-radio-wrapper` (value=`1`) | `1` | 已选中 ✅ |
| 好友可见 | `.ant-radio-wrapper` (value=`4`) | `4` | 未选中 |
| 仅自己可见 | `.ant-radio-wrapper` (value=`2`) | `2` | 未选中 |

**容器:** 第一个 `.ant-radio-group.ant-radio-group-outline`
**表单标签:** `._label_1quq7_19` (文本="查看权限")

**自动化操作方式:**
```javascript
// 切换到"仅自己可见"
document.querySelector('.ant-radio-input[value="2"]').click();
```

**判断状态:**
```javascript
const radioWrapper = document.querySelector('.ant-radio-wrapper');
const isSelected = radioWrapper.classList.contains('ant-radio-wrapper-checked');
```

---

## 十、发布时间（重点：定时发布）

### 10.1 发布时间 Radio 选择

| 选项 | CSS 选择器 | input value | 说明 |
|------|----------|------------|------|
| 立即发布 | `.ant-radio-input[value="1"]` | `1` | 选择后隐藏时间选择器 |
| 定时发布 | `.ant-radio-input[value="2"]` | `2` | 选择后显示时间选择器 |

**容器:** `._publish-time-container_171ix_408` 内的 `.ant-radio-group`
**表单项容器:** `._edit-form-item_171ix_7._publish-time_171ix_401`
**表单标签:** `._label_171ix_19` (文本="发布时间")

**自动化操作方式 - 切换到定时发布:**
```javascript
// 点击"定时发布"
document.querySelector('.ant-radio-input[value="2"]').click();
```

### 10.2 日期时间选择器（DatePicker）

| 属性 | 值 |
|------|-----|
| **CSS选择器** | `.ant-picker._data-picker_171ix_411` |
| **input选择器** | `.ant-picker._data-picker_171ix_411 input` |
| **placeholder** | "选择日期时间" |
| **日期格式** | `YYYY-MM-DD HH:mm:ss` (例: "2026-03-09 17:03:00") |
| **后缀图标** | `.ant-picker-suffix` → `.anticon-clock-circle` |
| **清除按钮** | `.ant-picker-clear` (role="button") → `.anticon-close-circle` |
| **聚焦状态类** | `ant-picker-focused` |

**自动化操作方式 - 通过直接修改input值:**
```javascript
// 方法1：直接设置input值（推荐）
const pickerInput = document.querySelector('.ant-picker._data-picker_171ix_411 input');
const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
nativeInputValueSetter.call(pickerInput, '2026-03-15 10:00:00');
pickerInput.dispatchEvent(new Event('input', { bubbles: true }));
pickerInput.dispatchEvent(new Event('change', { bubbles: true }));
```

### 10.3 定时选择器弹窗（DatePicker Dropdown）★★★ 重点

点击日期时间输入框后弹出的时间选择弹窗：

#### 10.3.1 弹窗容器

| 属性 | 值 |
|------|-----|
| **弹窗CSS选择器** | `.ant-picker-dropdown` |
| **定位类** | `ant-picker-dropdown-placement-topLeft` (弹窗在输入框上方) |
| **style定位** | `left: 589px; top: 132px;` (绝对定位) |
| **面板容器** | `.ant-picker-panel-container` → `.ant-picker-panel` → `.ant-picker-datetime-panel` |

#### 10.3.2 日期面板（左侧）

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 日期面板 | `.ant-picker-date-panel` | |
| 头部导航 | `.ant-picker-header` | |
| **上一年按钮** | `.ant-picker-header-super-prev-btn` | 图标: `.ant-picker-super-prev-icon` (双左箭头 «) |
| **上一月按钮** | `.ant-picker-header-prev-btn` | 图标: `.ant-picker-prev-icon` (左箭头 ‹) |
| **年份按钮** | `.ant-picker-year-btn` | 文本例: "2026年"，点击可切换年份面板 |
| **月份按钮** | `.ant-picker-month-btn` | 文本例: "3月"，点击可切换月份面板 |
| **下一月按钮** | `.ant-picker-header-next-btn` | 图标: `.ant-picker-next-icon` (右箭头 ›) |
| **下一年按钮** | `.ant-picker-header-super-next-btn` | 图标: `.ant-picker-super-next-icon` (双右箭头 ») |
| 日历主体 | `.ant-picker-body` → `table.ant-picker-content` | |
| 星期行 | `thead > tr > th` | 一、二、三、四、五、六、日 |
| 日期单元格 | `td.ant-picker-cell` | |
| 日期单元格内文字 | `.ant-picker-cell-inner` | |

**日期单元格状态类:**

| 类名 | 含义 |
|------|------|
| `ant-picker-cell-in-view` | 当前月份的日期（可见/可选） |
| `ant-picker-cell-today` | 今天 |
| `ant-picker-cell-selected` | 当前选中的日期 |
| `ant-picker-cell-disabled` | 不可选的日期（已过期或超出范围） |
| `ant-picker-cell-start` | 月份起始日 |
| `ant-picker-cell-end` | 月份结束日 |

**日期范围限制:** 从截图分析来看，快手定时发布有如下限制:
- 过去的日期被 disabled（如 3月1日-3月8日）
- 超过约 14 天后的日期被 disabled（如 3月22日之后）
- 实际可选范围约为 **当前时间 ~ 未来13天**

**自动化操作方式 - 选择日期:**
```javascript
// 方法：点击日期选择器打开弹窗，然后点击目标日期
const pickerInput = document.querySelector('.ant-picker._data-picker_171ix_411 input');
pickerInput.click(); // 打开弹窗

// 等待弹窗出现
await new Promise(r => setTimeout(r, 300));

// 选择指定日期（通过 title 属性定位）
const targetDate = document.querySelector('.ant-picker-cell[title="2026-03-15"]');
if (targetDate && !targetDate.classList.contains('ant-picker-cell-disabled')) {
    targetDate.querySelector('.ant-picker-cell-inner').click();
}
```

#### 10.3.3 时间面板（右侧）

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 时间面板 | `.ant-picker-time-panel` | |
| 时间头部显示 | `.ant-picker-time-panel .ant-picker-header-view` | 显示当前时间，如 "17:03:00" |
| 时间列容器 | `.ant-picker-content` (在时间面板内) | |
| **小时列** | `.ant-picker-time-panel-column:nth-child(1)` | 24项 (00-23) |
| **分钟列** | `.ant-picker-time-panel-column:nth-child(2)` | 60项 (00-59) |
| **秒钟列** | `.ant-picker-time-panel-column:nth-child(3)` | 60项 (00-59) |

**时间列结构:**
```
ul.ant-picker-time-panel-column
  └─ li.ant-picker-time-panel-cell
       └─ div.ant-picker-time-panel-cell-inner  (文本: "00"/"01"/..."23")
```

**时间单元格状态类:**

| 类名 | 含义 |
|------|------|
| `ant-picker-time-panel-cell-selected` | 当前选中的时间项 |
| `ant-picker-time-panel-cell-disabled` | 不可选的时间项 |

**自动化操作方式 - 选择时间:**
```javascript
// 选择小时 = 10
const hourColumn = document.querySelector('.ant-picker-time-panel-column:nth-child(1)');
const hourCells = hourColumn.querySelectorAll('.ant-picker-time-panel-cell');
hourCells[10].querySelector('.ant-picker-time-panel-cell-inner').click(); // 选10点

// 选择分钟 = 30
const minuteColumn = document.querySelector('.ant-picker-time-panel-column:nth-child(2)');
const minuteCells = minuteColumn.querySelectorAll('.ant-picker-time-panel-cell');
minuteCells[30].querySelector('.ant-picker-time-panel-cell-inner').click(); // 选30分

// 选择秒 = 0
const secondColumn = document.querySelector('.ant-picker-time-panel-column:nth-child(3)');
const secondCells = secondColumn.querySelectorAll('.ant-picker-time-panel-cell');
secondCells[0].querySelector('.ant-picker-time-panel-cell-inner').click(); // 选0秒
```

#### 10.3.4 确定按钮

| 属性 | 值 |
|------|-----|
| **CSS选择器** | `.ant-picker-ok button` |
| **按钮类** | `ant-btn ant-btn-primary ant-btn-sm` |
| **文本** | "确定" |
| **容器** | `.ant-picker-ok` |

**自动化操作方式 - 点击确定:**
```javascript
document.querySelector('.ant-picker-ok button').click();
```

### 10.4 完整定时发布自动化流程 ★★★

```javascript
async function setScheduledPublish(dateStr, hour, minute, second = 0) {
    // 步骤1: 选择"定时发布"
    const scheduledRadio = document.querySelector('.ant-radio-input[value="2"]');
    if (!scheduledRadio.checked) {
        scheduledRadio.click();
        await new Promise(r => setTimeout(r, 300));
    }

    // 步骤2: 点击日期选择器打开弹窗
    const pickerInput = document.querySelector('.ant-picker._data-picker_171ix_411 input');
    pickerInput.click();
    await new Promise(r => setTimeout(r, 500));

    // 步骤3: 选择日期（通过title属性精确匹配）
    const targetCell = document.querySelector(`.ant-picker-cell[title="${dateStr}"]`);
    if (targetCell && !targetCell.classList.contains('ant-picker-cell-disabled')) {
        targetCell.querySelector('.ant-picker-cell-inner').click();
        await new Promise(r => setTimeout(r, 300));
    }

    // 步骤4: 选择小时
    const hourCol = document.querySelector('.ant-picker-time-panel-column:nth-child(1)');
    hourCol.querySelectorAll('.ant-picker-time-panel-cell')[hour]
        .querySelector('.ant-picker-time-panel-cell-inner').click();
    await new Promise(r => setTimeout(r, 200));

    // 步骤5: 选择分钟
    const minCol = document.querySelector('.ant-picker-time-panel-column:nth-child(2)');
    minCol.querySelectorAll('.ant-picker-time-panel-cell')[minute]
        .querySelector('.ant-picker-time-panel-cell-inner').click();
    await new Promise(r => setTimeout(r, 200));

    // 步骤6: 选择秒
    const secCol = document.querySelector('.ant-picker-time-panel-column:nth-child(3)');
    secCol.querySelectorAll('.ant-picker-time-panel-cell')[second]
        .querySelector('.ant-picker-time-panel-cell-inner').click();
    await new Promise(r => setTimeout(r, 200));

    // 步骤7: 点击确定
    document.querySelector('.ant-picker-ok button').click();
}

// 使用示例: 设置为 2026-03-15 10:30:00 定时发布
await setScheduledPublish('2026-03-15', 10, 30, 0);
```

---

## 十一、底部操作按钮

| 按钮 | CSS 选择器 | 说明 |
|------|----------|------|
| **发布按钮** | `._button_3a3lq_1._button-primary_3a3lq_60` | 粉色/红色主按钮 |
| **取消按钮** | `._button_3a3lq_1._button-default_3a3lq_35` | 白色默认按钮 |
| 按钮容器 | `._edit-section-btns_ql0z6_118` | |

**注意:** 发布和取消按钮是 `<div>` 不是 `<button>`！

**自动化操作方式:**
```javascript
// 点击发布
document.querySelector('._edit-section-btns_ql0z6_118 ._button-primary_3a3lq_60').click();

// 点击取消
document.querySelector('._edit-section-btns_ql0z6_118 ._button-default_3a3lq_35').click();
```

---

## 十二、右侧预览区域

### 12.1 视频预览

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 预览容器 | `._preview_1eni7_87` | |
| 重新上传按钮 | `._preview-btns_1eni7_113` 内的 `._button-default_3a3lq_35` | 文本="重新上传" |

### 12.2 画质增强

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 画质增强标题 | `._ratio-header_3e2zd_54` | 文本="画质增强" |
| 画质预览开关 | `.ant-switch.ant-switch-small._switch_3e2zd_88` | 文本="预览", aria-checked判断状态 |

### 12.3 创作助手面板

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 助手容器 | `._helper_1kfmm_1` | |
| 助手背景 | `._helper-background_1kfmm_14` | |
| 助手头部 | `._helper-header_1kfmm_25` | |
| 助手标题 | `._helper-header-title_1kfmm_38` (文本="创作助手") | |
| 助手主区域 | `._helper-main_1kfmm_68` | |
| 流量提升建议 | `._flow_16saw_2` | "去优化标题" 等建议 |

---

## 十三、使用向导/引导层（Guide/Tour）

快手发布页面首次使用时会弹出使用向导，共4步。

### 13.1 向导组件（基于 react-joyride）

| 元素 | CSS 选择器 | 说明 |
|------|----------|------|
| 遮罩层 | `.react-joyride__overlay` | 半透明背景遮罩 |
| 高亮区 | `.react-joyride__spotlight` | 高亮当前步骤对应的元素 |
| 提示框容器 | `[class*="_tooltip_d7f44"]` | 向导提示内容 |
| 步骤标识 | 文本 "1/4"、"2/4"、"3/4"、"4/4" | 显示当前步骤 |
| 标题文字 | "作品信息" 等 | 每步主题 |
| 说明文字 | "便捷填写作品关键信息" 等 | 每步说明 |
| "下一步" 按钮 | 向导提示框内的按钮 | 红色主按钮 |

**自动化操作方式 - 跳过向导:**
```javascript
// 方法1: 查找并点击"下一步"按钮直到向导结束
async function skipGuide() {
    for (let i = 0; i < 4; i++) {
        const nextBtn = document.evaluate(
            "//button[contains(text(),'下一步')] | //button[contains(text(),'知道了')]",
            document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
        ).singleNodeValue;
        if (nextBtn) {
            nextBtn.click();
            await new Promise(r => setTimeout(r, 500));
        }
    }
}
```

---

## 十四、选择器汇总表（所有 ant-select 组件）

| 用途 | input ID | placeholder | 可搜索 | 默认disabled |
|------|---------|------------|--------|-------------|
| 作者服务-服务类型 | `rc_select_4` | 选择服务类型 | 否 | 否 |
| 作者服务-关联收益 | `rc_select_5` | 关联成功可获得更多收益 | 是 | **是** |
| 关联热点 | `rc_select_0` | 输入你想关联的热点 | 是 | 否 |
| 作者声明 | `rc_select_1` | 为作品添加补充说明 | 否 | 否 |
| 添加地点-地区 | `rc_select_2` | 请选择所在地区 | 是 | 否 |
| 添加地点-详细地址 | `rc_select_3` | 请输入视频详细地址，让同城老铁看见你 | 是 | **是** |

**注意:** `rc_select_*` 的ID是由 antd 动态生成的，数字可能会随页面加载顺序变化。建议使用 **placeholder** 文本结合父容器定位更稳定:
```javascript
// 稳定的选择器方式
document.querySelector('.ant-select-selection-search-input[placeholder="输入你想关联的热点"]');
// 或者通过 aria-owns 属性
document.querySelector('[aria-owns="rc_select_0_list"]');
```

---

## 十五、完整自动发布示例代码

```javascript
async function autoPublishVideo(options = {}) {
    const {
        description = '',        // 作品描述
        topics = [],             // 话题标签数组
        visibility = '1',        // '1'=所有人, '4'=好友, '2'=仅自己
        allowSameFrame = true,   // 允许同框
        allowDownload = true,    // 允许下载
        showNearby = true,       // 展示同城
        publishMode = 'now',     // 'now'=立即, 'scheduled'=定时
        scheduledDate = '',      // 定时日期 'YYYY-MM-DD'
        scheduledHour = 10,      // 定时小时
        scheduledMinute = 0,     // 定时分钟
    } = options;

    const delay = ms => new Promise(r => setTimeout(r, ms));

    // 1. 跳过向导（如存在）
    for (let i = 0; i < 5; i++) {
        const guideBtn = document.evaluate(
            "//button[contains(text(),'下一步')] | //button[contains(text(),'知道了')]",
            document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
        ).singleNodeValue;
        if (guideBtn) { guideBtn.click(); await delay(400); }
        else break;
    }

    // 2. 填写描述
    const desc = document.querySelector('._description_17g9x_24');
    if (desc && description) {
        desc.focus();
        desc.innerHTML = description;
        desc.dispatchEvent(new Event('input', { bubbles: true }));
        await delay(300);
    }

    // 3. 设置互动选项
    const checkboxMap = { allowSameFrame: 'allowSameFrame', allowDownload: 'downloadType', showNearby: 'disableNearbyShow' };
    for (const [key, value] of Object.entries({ allowSameFrame, allowDownload, showNearby })) {
        const cb = document.querySelector(`.ant-checkbox-input[value="${checkboxMap[key]}"]`);
        if (cb && cb.checked !== value) cb.click();
    }
    await delay(200);

    // 4. 设置查看权限
    document.querySelector(`.ant-radio-input[value="${visibility}"]`).click();
    await delay(200);

    // 5. 设置发布时间
    if (publishMode === 'scheduled') {
        document.querySelector('.ant-radio-input[value="2"]').click();
        await delay(500);

        const pickerInput = document.querySelector('.ant-picker._data-picker_171ix_411 input');
        pickerInput.click();
        await delay(500);

        // 选日期
        const cell = document.querySelector(`.ant-picker-cell[title="${scheduledDate}"]`);
        if (cell && !cell.classList.contains('ant-picker-cell-disabled')) {
            cell.querySelector('.ant-picker-cell-inner').click();
            await delay(300);
        }

        // 选时间
        const cols = document.querySelectorAll('.ant-picker-time-panel-column');
        cols[0].querySelectorAll('.ant-picker-time-panel-cell')[scheduledHour]
            .querySelector('.ant-picker-time-panel-cell-inner').click();
        await delay(200);
        cols[1].querySelectorAll('.ant-picker-time-panel-cell')[scheduledMinute]
            .querySelector('.ant-picker-time-panel-cell-inner').click();
        await delay(200);
        cols[2].querySelectorAll('.ant-picker-time-panel-cell')[0]
            .querySelector('.ant-picker-time-panel-cell-inner').click();
        await delay(200);

        document.querySelector('.ant-picker-ok button').click();
        await delay(300);
    } else {
        document.querySelector('.ant-radio-input[value="1"]').click();
        await delay(200);
    }

    // 6. 点击发布
    document.querySelector('._edit-section-btns_ql0z6_118 ._button-primary_3a3lq_60').click();
}

// 调用示例
await autoPublishVideo({
    description: '这是我的视频描述 #话题标签',
    visibility: '1',
    publishMode: 'scheduled',
    scheduledDate: '2026-03-15',
    scheduledHour: 10,
    scheduledMinute: 30,
});
```

---

## 附录：注意事项

1. **CSS类名包含哈希值:** 快手使用 CSS Modules，类名后缀的哈希值（如 `_17g9x_24`）在页面版本更新后可能变化。建议使用前缀匹配如 `[class*="_description_"]` 增加兼容性。

2. **ant-select 的 ID 动态生成:** `rc_select_*` 的数字是动态分配的，建议优先通过 placeholder 或父容器定位。

3. **React 状态同步:** 直接修改 DOM 可能不会触发 React 状态更新。对于 input 元素，建议使用原生 `nativeInputValueSetter` 配合事件派发。

4. **定时发布时间限制:** 可选时间范围约为当前时间后 ~13天内，超出范围的日期会被 disabled。

5. **操作节奏:** 自动化操作之间建议添加 200-500ms 延迟，避免因页面渲染未完成导致操作失败。

6. **发布/取消按钮是 div:** 快手使用自定义的 div 按钮而非原生 button，直接 `.click()` 即可。
