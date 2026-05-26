# -*- coding: utf-8 -*-
"""「更多发布设置」卡片布局常量（与单条页旧「发布设置」视觉对齐，独立维护便于日后删旧卡）。"""

LABEL_WIDTH = 72
ROW_GAP = 14
H_GAP = 10
# 左栏每一设置行统一最小高度（与 ComboBox 单行对齐）
SHARED_ROW_MIN_HEIGHT = 32
# 左右分栏：左侧共用设置略宽，右侧平台相关
SPLIT_LEFT_STRETCH = 3
SPLIT_RIGHT_STRETCH = 2
SPLIT_COLUMN_GAP = 12
DIVIDER_WIDTH = 2
# 分栏竖线颜色（浅灰，深浅主题下均可见）
DIVIDER_COLOR = "#C5C5C5"
COMBO_WIDTH = 220  # 作品申明等宽下拉
SHARED_LEFT_COMBO_WIDTH = 120  # 左栏：位置 / 带货推广 / 设置权限 下拉统一宽度
TAG_TYPE_COMBO_WIDTH = 88
LOCATION_MODE_COMBO_WIDTH = 108
LOCATION_LINEEDIT_MAX_WIDTH = 420

# 右栏抖音位置特殊区标题（醒目红色，避免用户忽视）
DOUYIN_LOCATION_SPECIAL_LABEL = "抖音位置特殊设置"

# 抖音：位置推广（poi）与左侧「带货推广」不可同时启用
DOUYIN_LOC_PROMO_MUTEX_HINT_WHEN_LOCATION = (
    "抖音已选位置推广，不可同时使用「带货推广」"
)
DOUYIN_LOC_PROMO_MUTEX_HINT_WHEN_PROMOTION = (
    "抖音已开启带货推广，请先将带货改为「无」再选位置"
)
DOUYIN_LOCATION_SPECIAL_LABEL_STYLE = "color: #E53935; font-weight: 600; font-size: 13px;"
DOUYIN_LOCATION_SPECIAL_LABEL_WIDTH = 120

# 混平台账号组：左栏申明提示（实际操作在右栏）
MIXED_GROUP_WD_LEFT_HINT = "请在右侧设置"
WD_LEFT_HINT_SELECT_TARGET = "请先选择发布对象"
ORIGINAL_LEFT_HINT_NOT_APPLICABLE = "当前平台无需申明原创"
WD_LEFT_HINT_WECHAT_USE_ORIGINAL = "请在上方「原创声明」中设置"
WD_LEFT_HINT_NOT_APPLICABLE = "当前平台无需设置作品申明"

LOCATION_MODE_TAG_KEY = "位置_模式"
CART_PROMOTION_TITLE_TAG_KEY = "购物车_推广标题"
TUAN_PROMOTION_TITLE_TAG_KEY = "团购_推广标题"
CART_PROMOTION_TITLE_MAX_LEN = 10
