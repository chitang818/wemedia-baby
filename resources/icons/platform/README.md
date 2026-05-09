# 平台图标

将各平台官方/品牌 Logo 放置于此目录后，添加账号对话框的「热门平台」卡片将显示真实图标。

## 一键生成（推荐）

在项目根目录执行：

```bash
python scripts/dev/download_platform_icons.py
```

脚本会从 [Simple Icons](https://simpleicons.org)（CC0）下载抖音、微信、快手、小红书的 SVG 并转为 PNG 到此目录。需已安装 PySide6。

## 手动放置

| 文件名 | 对应平台 |
|--------|----------|
| `douyin.png` | 抖音 |
| `wechat_video.png` | 视频号 |
| `kuaishou.png` | 快手 |
| `xiaohongshu.png` | 小红书 |

建议尺寸：**64×64** 或 **128×128** 像素，透明背景 PNG。

## 获取图标

- **Simple Icons**（CC0，可商用）：https://simpleicons.org  
  搜索 Douyin、Kuaishou、Xiaohongshu、WeChat，下载 PNG 或 SVG 后转为 PNG 即可。
- 或从各品牌官网/媒体资源页下载官方 Logo，注意遵守品牌使用规范。

未放置对应文件时，界面将使用 emoji 作为占位图标。
