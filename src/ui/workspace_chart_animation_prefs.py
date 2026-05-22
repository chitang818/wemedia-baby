"""
工作台图表加载与入场动画参数。
"""

from __future__ import annotations

# 与 LoadingOverlay._FADE_MS 对齐
CHART_OVERLAY_FADE_MS = 200

# QChart.setAnimationDuration：入场动画时长（避免默认 1000ms）
CHART_ENTRY_ANIMATION_MS = 400

# 第二张图 reveal 错峰，避免同帧抢绘制
CHART_STAGGER_MS = 80

# 后台刷新时 loading 最短展示，避免闪烁
CHART_MIN_LOADING_MS_REFRESH = 150

# 统计卡片骨架最短展示（避免数据过快返回时闪烁）
STATS_SKELETON_MIN_MS = 180

# 数值淡入时长（与遮罩淡出对齐）
STATS_VALUE_FADE_MS = 200
