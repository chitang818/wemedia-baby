# -*- coding: utf-8 -*-
"""
视频号创作者中心 / 发布页使用的 wujie-app Shadow 根节点解析。

与 docs/03插件系统/3.2插件选择器标准化规范.md 第 5.1 节一致：统一宿主路径降级顺序，
避免各 step 内复制粘贴的 IIFE 不一致导致命中错误 shadow。

用法：在 page.evaluate 的 JS 字符串中插入本常量，例如：
    f\"\"\"() => {{
        const shadow = {WUJIE_SHADOW_ROOT_JS};
        if (!shadow) return 'no_shadow';
        ...
    }}\"\"\"
"""

# 返回 ShadowRoot | null 的立即执行函数表达式（末尾已带调用括号）
WUJIE_SHADOW_ROOT_JS = """
(function() {
    var paths = [
        '#container-wrap > div.container-center > div > div.main-body > div.third-line > div > wujie-app',
        '#container-wrap > div.container-center > div > wujie-app'
    ];
    for (var i = 0; i < paths.length; i++) {
        var w = document.querySelector(paths[i]);
        if (w && w.shadowRoot) return w.shadowRoot;
    }
    var all = document.querySelectorAll('wujie-app');
    for (var j = 0; j < all.length; j++) {
        if (all[j].shadowRoot) return all[j].shadowRoot;
    }
    return null;
})()
""".strip()

# Playwright page.evaluate_handle(selector) 用：在统一 shadow 内 querySelector
WUJIE_SHADOW_QUERY_SELECTOR_FN_JS = (
    "(selector) => {\n"
    "    const shadow = "
    + WUJIE_SHADOW_ROOT_JS
    + ";\n"
    "    if (!shadow) return null;\n"
    "    return shadow.querySelector(selector);\n"
    "}"
)

# SubmitStep：在 shadow 内解析底部「发表」按钮（排除「手机预览」「保存草稿」等相邻误触目标）
# 策略：form-btns 内文案严格等于「发表」→ 优先 weui-desktop-btn_primary → 同文案多枚时取最靠右
WUJIE_SHADOW_RESOLVE_SUBMIT_BTN_JS = (
    "() => {\n"
    "    const shadow = "
    + WUJIE_SHADOW_ROOT_JS
    + ";\n"
    "    if (!shadow) return null;\n"
    "    var bar = shadow.querySelector('div.form-btns');\n"
    "    var scope = bar || shadow;\n"
    "    var bad = { '手机预览': 1, '保存草稿': 1 };\n"
    "    var buttons = scope.querySelectorAll('button');\n"
    "    var hits = [];\n"
    "    for (var i = 0; i < buttons.length; i++) {\n"
    "        var b = buttons[i];\n"
    "        var t = (b.innerText || b.textContent || '').replace(/\\s+/g, '').trim();\n"
    "        if (bad[t]) continue;\n"
    "        if (t.indexOf('手机预览') !== -1) continue;\n"
    "        if (t !== '发表') continue;\n"
    "        var r = b.getBoundingClientRect();\n"
    "        if (r.width < 2 || r.height < 2) continue;\n"
    "        var st = window.getComputedStyle(b);\n"
    "        if (st.visibility === 'hidden' || st.display === 'none') continue;\n"
    "        hits.push(b);\n"
    "    }\n"
    "    if (!hits.length) return null;\n"
    "    var prim = hits.filter(function(b) {\n"
    "        return b.classList && b.classList.contains('weui-desktop-btn_primary');\n"
    "    });\n"
    "    var pool = prim.length ? prim : hits;\n"
    "    pool.sort(function(a, b) {\n"
    "        return b.getBoundingClientRect().right - a.getBoundingClientRect().right;\n"
    "    });\n"
    "    return pool[0];\n"
    "}"
)
