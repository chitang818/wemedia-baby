# 抖音发布步骤包（视频/图文均为 8 步）
#
# ========== 主链用的（发布流程实际执行的） ==========
# 步骤1  step_01_home.py          导航首页（打开创作者中心）
# 步骤2  step_02_entry.py         进入发布页（点「发布视频」或「发布图文」）
# 步骤3  step_03_upload.py        上传（上传视频或图文文件）
# 步骤4  step_04_description.py   填写描述（标题/正文/话题）
# 步骤5  step_05_cover_video.py   封面设置-视频   ┐ 按 file_type 二选一
#        step_05_cover_image.py   封面设置-图文   ┘
# 步骤6  扩展信息（视频：6b+6c；图文：6a+6b+6c；各子步骤内部自行跳过无关字段）
#        step_06a_music.py        图文专用：选择背景音乐
#        step_06b_extra_info.py   视频/图文通用：添加标签（位置/团购/购物车/小程序）
#        step_06c_trending.py     视频/图文通用：关联热点（TODO：功能待实现，当前为占位）
# 步骤7  step_07_settings.py      发布设置（定时/可见性/保存权限）
# 步骤8  step_08_submit.py        点击发布（提交并验证结果）
#
# 辅助   _base.py                 步骤基类（所有步骤继承用）
# 辅助   step_runner.py           步骤运行器（不是步骤！负责按顺序执行步骤列表）
