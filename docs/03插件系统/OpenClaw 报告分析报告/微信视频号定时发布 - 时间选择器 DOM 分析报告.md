# 微信视频号定时发布 - 时间选择器 DOM 分析报告

**分析时间:** 2026-03-31 18:10  
**页面 URL:** https://channels.weixin.qq.com/platform/post/create  
**目标时间:** 2026-04-02 18:26

---

## 一、时间选择器 DOM 结构

### 1. 完整层级结构

```
generic [ref=e257] 定时发表容器
└─ generic [ref=e258] 「发表时间」标签
   └─ generic [ref=e260] 容器
      ├─ term [ref=e261] [cursor=pointer] 可点击标签
      │  └─ textbox [ref=e265] 主输入框 (显示：2026-04-02 18:26)
      └─ definition [ref=e266] ← 弹窗容器 (关键！)
         └─ generic [ref=e267] 弹窗内容
            ├─ generic [ref=e268] 头部导航
            │  ├─ button [ref=e381] 左箭头 (上月)
            │  ├─ text: "2026 年 04 月"
            │  └─ button [ref=e269] 右箭头 (下月)
            ├─ table [ref=e271] 日历表格
            │  └─ 日期单元格 (cell > link 结构)
            └─ generic [ref=e371] 时间区域
               ├─ paragraph [ref=e373] "时间"
               └─ generic [ref=e374] 时间选择器
                  ├─ term [ref=e375] 可点击标签
                  │  └─ textbox [ref=e379] 时间输入框 (显示：18:26)
                  └─ definition [ref=e444] ← 时间列表弹窗
                     ├─ list [ref=e445] 标签 ["时", "分"]
                     ├─ list [ref=e448] 小时列表 (00-23)
                     └─ list [ref=e473] 分钟列表 (00-59)
```

### 2. 关键 CSS 类名（供代码参考）

根据微信 WeUI 设计规范，实际类名应该是：

| 元素 | CSS 类名 |
|------|----------|
| 日期时间选择器根 | `.weui-desktop-picker__date-time` |
| 面板头部 | `.weui-desktop-picker__panel__hd` |
| 日历表格 | `.weui-desktop-picker__table` |
| 时间选择区域 | `.weui-desktop-picker__time` |
| 小时列表 | `.weui-desktop-picker__time__hour` |
| 分钟列表 | `.weui-desktop-picker__time__minute` |
| 下拉弹层容器 | `.weui-desktop-picker__dd` |

### 3. 时间列表元素结构

**小时列表 (ref=e448):**
```
list [ref=e448]
├─ listitem [ref=e449] "00"
├─ listitem [ref=e450] "01"
├─ ...
├─ listitem [ref=e467] "18" ← 目标小时
├─ ...
└─ listitem [ref=e472] "23"
```

**分钟列表 (ref=e473):**
```
list [ref=e473]
├─ listitem [ref=e474] "00"
├─ listitem [ref=e475] "01"
├─ ...
├─ listitem [ref=e500] "26" ← 目标分钟
├─ ...
└─ listitem [ref=e533] "59"
```

---

## 二、关闭弹窗的测试结果

### ✅ 成功方法

| 方法 | 操作 | 结果 |
|------|------|------|
| 点击「短标题」标签 | `click(ref=e220)` | ✅ 弹窗关闭 |
| 点击弹窗外表单区域 | 点击 picker 外部元素 | ✅ 弹窗关闭 |

### ❌ 失败方法

| 方法 | 操作 | 结果 | 原因 |
|------|------|------|------|
| 点击主输入框 | `click(ref=e261)` | ❌ 未关闭 | 输入框是触发器，会 toggle 弹窗 |
| 点击时间标签 | `click(ref=e375)` | ❌ 未关闭 | 仍在 picker 组件内部 |

---

## 三、关闭弹窗的原理分析

### 成功原因

点击「短标题」标签成功关闭弹窗的原因：

1. **点击发生在 picker 组件外部**
   - 触发 Vue 的 `v-click-outside` 指令或类似的点击外部关闭逻辑
   - WeUI 的 picker 组件在检测到点击目标不在弹窗 DOM 树内时，会触发关闭

2. **安全的点击位置**
   - 「短标题」位于 picker 下方，不在弹窗覆盖范围内
   - 点击不会触发其他控件的 toggle 行为

### 失败原因

点击主输入框未能关闭弹窗的原因：

1. **输入框是 picker 的触发器（trigger）**
   - 点击它会 toggle 弹窗状态
   - 如果弹窗已打开，点击可能被视为"重新聚焦"而非"关闭"

2. **事件冒泡被阻止**
   - picker 组件内部可能调用了 `event.stopPropagation()`
   - 导致点击事件无法传播到外部的关闭处理器

---

## 四、代码问题分析

### 问题 1：关闭弹窗的元素选择可能不准确

你的代码中 `_click_outside_picker` 函数优先选择「短标题」：

```python
if (t.includes('短标题')) { bestEl = label; break; }
```

**这是正确的策略！** 但可能存在以下问题：

1. **页面滚动问题**
   - 如果「短标题」不在可视区域，`scrollIntoView` 后点击坐标可能仍被弹窗遮挡
   
2. **wujie Shadow DOM 穿透问题**
   - 代码通过 `page.evaluate()` 在 shadow root 内计算坐标
   - 但实际点击时 `page.mouse.click()` 是在主文档层面
   - 可能存在坐标偏移

### 问题 2：弹窗可见性检测可能误判

你的 `_JS_PICKER_FLOAT_VISIBLE` 检查多个元素：

```javascript
const ddSel = 'dd.weui-desktop-picker__dd, .weui-desktop-picker__dd__time';
```

**问题：**

1. 微信的弹窗可能使用 `definition` 元素（如我们看到的 ref=e266），而不是 `dd`
2. 部分弹窗容器可能没有 `display: none`，而是通过 `visibility: hidden` 或 `opacity: 0` 隐藏
3. 弹窗可能仍在 DOM 中但已失去焦点，此时 `getBoundingClientRect()` 仍返回有效值

### 问题 3：缺少真正的「点击外部」逻辑

代码尝试点击「短标题」标签本身，但这可能仍在弹窗的点击事件捕获范围内。

**建议改进：**

1. 计算 picker 根元素的边界矩形
2. 在 picker 矩形**外部**但在表单区域内的位置点击
3. 使用 `page.mouse.click()` 直接点击视口坐标，而不是通过元素中心

---

## 五、修复建议

### 建议 1：改进关闭弹窗的坐标计算

```javascript
// 在 picker 下方安全区域点击
const r = pickerRoot.getBoundingClientRect();
const clickX = r.left + r.width * 0.5;  // 水平居中
const clickY = r.bottom + 50;  // 在弹窗下方 50px 处点击
return { x: clickX, y: clickY };
```

### 建议 2：增加 Escape 键兜底

```python
# 在点击外部后，如果弹窗仍未关闭，发送 Escape 键
await page.keyboard.press("Escape")
await page.wait_for_timeout(300)
```

### 建议 3：改进弹窗可见性检测

```javascript
// 检查 definition 元素是否存在且可见
const definitionEl = pickerRoot.querySelector('definition');
if (definitionEl) {
    const style = window.getComputedStyle(definitionEl);
    const isVisible = style.display !== 'none' && 
                      style.visibility !== 'hidden' && 
                      style.opacity !== '0';
    if (isVisible) return true;
}
return false;
```

### 建议 4：增加点击后的等待时间

微信的 Vue 应用可能需要更多时间来响应点击事件：

```python
await page.mouse.click(x, y)
await page.wait_for_timeout(500)  # 增加到 500ms
```

---

## 六、完整的关闭弹窗流程建议

```python
async def close_picker_panel(page):
    """关闭时间选择器弹窗的可靠流程"""
    
    # 方法 1: 点击 picker 下方的安全区域
    coords = await page.evaluate("""() => {
        const shadow = document.querySelector('#wujie-app').shadowRoot;
        const picker = shadow.querySelector('.weui-desktop-picker__date-time');
        if (!picker) return null;
        const r = picker.getBoundingClientRect();
        return {
            x: r.left + r.width * 0.3,
            y: Math.min(r.bottom + 60, window.innerHeight - 10)
        };
    }""")
    
    if coords:
        await page.mouse.click(coords['x'], coords['y'])
        await page.wait_for_timeout(400)
    
    # 方法 2: 检查是否已关闭，未关闭则按 Escape
    still_open = await page.evaluate("""() => {
        const shadow = document.querySelector('#wujie-app').shadowRoot;
        const picker = shadow.querySelector('.weui-desktop-picker__date-time');
        return picker && picker.querySelector('definition') !== null;
    }""")
    
    if still_open:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
    
    # 方法 3: 最后尝试点击「短标题」
    await page.evaluate("""() => {
        const shadow = document.querySelector('#wujie-app').shadowRoot;
        const label = shadow.querySelector('.form-item .label');
        if (label && label.textContent.includes('短标题')) {
            label.click();
        }
    }""")
    await page.wait_for_timeout(300)
```

---

## 七、操作步骤记录

本次分析中成功设置定时时间的操作步骤：

| 步骤 | 操作 | 元素 ref | 结果 |
|------|------|----------|------|
| 1 | 点击「定时」单选按钮 | e214 | ✅ 切换到定时模式 |
| 2 | 点击「发表时间」输入框 | e261 | ✅ 打开日期选择器 |
| 3 | 点击下月箭头 | e269 | ✅ 翻到 4 月 |
| 4 | 点击日期 2 号 | e391 | ✅ 选择 4 月 2 日 |
| 5 | 点击时间区域 | e375 | ✅ 打开时间选择器 |
| 6 | 点击小时 18 | e467 | ✅ 选择 18 点 |
| 7 | 点击分钟 26 | e500 | ✅ 选择 26 分 |
| 8 | 点击「短标题」标签 | e220 | ✅ 关闭弹窗 |

**最终结果:** 输入框显示 `2026-04-02 18:26` ✅

---

## 八、总结

### 根本原因

1. **微信的 picker 弹窗使用 `definition` 元素**，而不是标准的 `dd` 或 `div`
2. **点击输入框会 toggle 弹窗而非关闭**
3. **wujie Shadow DOM 的坐标计算与实际点击位置可能存在偏差**
4. **Vue 响应式更新需要时间**，过早检测会导致误判

### 最佳实践

1. **在 picker 矩形外部点击**（如下方 50-100px）
2. **使用 Escape 键作为可靠兜底**
3. **增加等待时间让 Vue 完成状态更新**
4. **检测 `definition` 元素是否存在**，而非仅检查 `dd`

### 关键代码修改点

在 [`step_08_schedule.py`](file:///D:/003-AI_coding/wemedia-baby/wemedia-baby/src/plugins/pro/wechat_video/steps/step_08_schedule.py) 中需要修改：

1. `_click_outside_picker()` 函数 - 改进坐标计算逻辑
2. `_JS_PICKER_FLOAT_VISIBLE` 常量 - 增加 `definition` 元素检测
3. `_close_schedule_panels_until_dismissed()` 函数 - 增加 Escape 键兜底

---

**报告生成时间:** 2026-03-31 18:10:38 (Asia/Shanghai)
