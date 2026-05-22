# 小红书发布步骤包
#
# ========== 主链用的（发布流程实际执行的） ==========
# 步骤1  step_01_home.py        导航首页（打开创作者服务平台）
# 步骤2  step_02_entry.py       进入发布页（点「发布笔记」）
# 步骤3  step_03_upload.py      上传（上传视频或图文文件）
# 步骤4  step_04_cover.py       封面设置（视频用）
# 步骤5  step_05_description.py 作品描述（标题、正文、话题）
# 步骤6  step_06A_original_declaration.py 原创申明（6A，占位）
#        step_06B_work_declaration.py   作品申明（6B，占位）
#        step_06C_location.py           添加地点（6C，占位）
# 步骤7  step_07_settings.py    发布设置（视频：可见性+定时；图文：合拍+正文复制+可见性+定时）
# 步骤8  step_08_submit.py      点击发布（提交并验证结果）
#
# 辅助   _base.py               步骤基类（所有步骤继承用）
# 辅助   step_runner.py         步骤运行器（不是步骤！负责按顺序执行 step_01～step_08）
