# 多多视频发布步骤包
#
# ========== 主链用的（发布流程实际执行的） ==========
# 步骤1  step_01_home.py        导航首页（打开多多视频创作者中心）
# 步骤2  step_02_entry.py       进入发布页（打开视频发布页面）
# 步骤3  step_03_upload.py      上传（上传视频文件）
# 步骤4  step_04_description.py 作品描述（标题、简介、标签）
# 步骤5  step_05_cover.py       封面设置（视频封面）
# 步骤6  step_06_settings.py    发布设置（商品关联、定时发布等）
# 步骤7  step_07_submit.py      点击发布（提交并验证结果）
#
# 辅助   _base.py               步骤基类（所有步骤继承用）
# 辅助   step_runner.py         步骤运行器（不是步骤！负责按顺序执行 step_01～step_07）
