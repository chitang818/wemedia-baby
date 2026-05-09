# 快手发布步骤包
#
# 步骤链按发布类型在 publish_plugin.py 动态组装：
#
#   【视频发布】共 11 步：
#     1 step_01_home             导航首页
#     2 step_02_entry            进入发布页
#     3 step_03_upload           上传视频
#     4 step_04_description      作品描述
#     5 step_05_cover            封面设置
#     6 step_06b_author_service  作者服务（含关联商品）
#     7 step_07_manage_hotspot   关联热点
#     8 step_08_author_statement 作者声明
#     9 step_09_location         添加地点
#    10 step_10_settings         发布设置
#    11 step_11_submit           点击发布
#
#   【图文发布】进度仍为 11 阶段；第 6 阶段内连续执行两个小步骤：
#     1~5  同上
#     6  step_06a_music → step_06b_author_service（6a 添加音乐；6b 作者服务；日志均为 [步骤6/11 …]）
#     7~11 同上（与视频的阶段编号一致）
#
# 辅助   _base.py       步骤基类（从 core 统一基类 re-export）
# 辅助   step_runner.py 步骤运行器（动态重建进度索引，确保 [步骤X/N] 编号准确）
# 辅助   wizard_utils.py 向导弹窗处理工具
#
# 注：原 step_05b_music.py → step_06a_music.py；原 step_06_author_service.py → step_06b_author_service.py
