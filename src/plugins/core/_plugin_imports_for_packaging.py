# -*- coding: utf-8 -*-
"""
打包用静态 import 清单。不参与运行时逻辑，仅用于 Nuitka/PyInstaller 等打包时
显式引用所有平台插件模块，确保被打包收集。在入口或打包脚本中 import 本模块即可。
"""
from __future__ import annotations

# community
from src.plugins.community.douyin import login_plugin as _douyin_login
from src.plugins.community.douyin import publish_plugin as _douyin_publish
from src.plugins.community.kuaishou import login_plugin as _kuaishou_login
from src.plugins.community.kuaishou import publish_plugin as _kuaishou_publish
# pro
from src.plugins.pro.wechat_video import login_plugin as _wechat_video_login
from src.plugins.pro.wechat_video import publish_plugin as _wechat_video_publish
from src.plugins.pro.xiaohongshu import login_plugin as _xiaohongshu_login
from src.plugins.pro.xiaohongshu import publish_plugin as _xiaohongshu_publish
from src.plugins.pro.bilibili import login_plugin as _bilibili_login
from src.plugins.pro.bilibili import publish_plugin as _bilibili_publish
from src.plugins.pro.weibo import login_plugin as _weibo_login
from src.plugins.pro.weibo import publish_plugin as _weibo_publish
from src.plugins.pro.toutiao import login_plugin as _toutiao_login
from src.plugins.pro.toutiao import publish_plugin as _toutiao_publish
from src.plugins.pro.baijiahao import login_plugin as _baijiahao_login
from src.plugins.pro.baijiahao import publish_plugin as _baijiahao_publish
from src.plugins.pro.duoduoshipin import login_plugin as _duoduoshipin_login
from src.plugins.pro.duoduoshipin import publish_plugin as _duoduoshipin_publish
from src.plugins.pro.qiehao import login_plugin as _qiehao_login
from src.plugins.pro.qiehao import publish_plugin as _qiehao_publish

__all__ = [
    "_douyin_login", "_douyin_publish",
    "_kuaishou_login", "_kuaishou_publish",
    "_wechat_video_login", "_wechat_video_publish",
    "_xiaohongshu_login", "_xiaohongshu_publish",
    "_bilibili_login", "_bilibili_publish",
    "_weibo_login", "_weibo_publish",
    "_toutiao_login", "_toutiao_publish",
    "_baijiahao_login", "_baijiahao_publish",
    "_duoduoshipin_login", "_duoduoshipin_publish",
    "_qiehao_login", "_qiehao_publish",
]
