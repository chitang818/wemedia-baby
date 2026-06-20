import re
import os

source_file = r"d:\003-AI_coding\wemedia-baby\WeMediaBaby\resources\docs\index.html"
target_dir = r"d:\003-AI_coding\wemedia-baby\WeMediaBaby\docs\宣传物料"
target_file = os.path.join(target_dir, "mp_article.html")

if not os.path.exists(target_dir):
    os.makedirs(target_dir)

with open(source_file, "r", encoding="utf-8") as f:
    html_content = f.read()

# 提取 <main class="content"> 或者 <div class="content"> 的内容
# 经过前面的查看，似乎是 <div class="content"> 或者 <main class="content">
content_match = re.search(r'<main class="content">(.*?)</main>', html_content, re.DOTALL)
if not content_match:
    content_match = re.search(r'<div class="content">(.*?)</div>\s*</body>', html_content, re.DOTALL)

if not content_match:
    print("未找到主体内容区 (content)！")
    exit(1)

body_html = content_match.group(1)

# 清除已有的多余 class（如果不清理，后面替换也行，但微信编辑器里干净更好）
# 我们这里主要用正则直接注入 style，然后把 class 属性拿掉或者保留
replacements = [
    (r'<h1([^>]*)>', r'<h1\1 style="font-size: 2.2em; border-bottom: 2px solid #0078D4; padding-bottom: 10px; margin-top: 0;">'),
    (r'<h2([^>]*)>', r'<h2\1 style="font-size: 1.8em; border-bottom: 1px solid #E1DFDD; padding-bottom: 5px; margin-top: 1.5em; margin-bottom: 0.5em;">'),
    (r'<h3([^>]*)>', r'<h3\1 style="font-size: 1.4em; color: #0078D4; margin-top: 1.5em; margin-bottom: 0.5em;">'),
    (r'<h4([^>]*)>', r'<h4\1 style="font-size: 1.1em; color: #444; margin-top: 1.5em; margin-bottom: 0.5em;">'),
    (r'<p([^>]*)>', r'<p\1 style="margin-bottom: 1em; line-height: 1.6; color: #333;">'),
    (r'<ul([^>]*)>', r'<ul\1 style="margin-bottom: 1em; padding-left: 2em; line-height: 1.6; color: #333;">'),
    (r'<ol([^>]*)>', r'<ol\1 style="margin-bottom: 1em; padding-left: 2em; line-height: 1.6; color: #333;">'),
    (r'<code([^>]*)>', r'<code\1 style="background-color: #eee; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; font-size: 0.9em;">'),
    (r'class="badge pro"', r'style="display: inline-block; background-color: #FFB900; color: #000; font-weight: bold; font-size: 12px; padding: 2px 6px; border-radius: 4px; margin-left: 8px; vertical-align: middle;"'),
    (r'class="badge"', r'style="display: inline-block; background-color: #E1DFDD; color: #333; font-size: 12px; padding: 2px 6px; border-radius: 4px; margin-left: 8px; vertical-align: middle;"'),
    (r'class="card"', r'style="background: #fff; border: 1px solid #E1DFDD; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);"'),
    (r'class="alert alert-warning"', r'style="padding: 15px; border-left: 4px solid #FFB900; background-color: #FFF9E6; margin-bottom: 20px; border-radius: 0 8px 8px 0;"'),
    (r'class="alert"', r'style="padding: 15px; border-left: 4px solid #0078D4; background-color: #F3F9FD; margin-bottom: 20px; border-radius: 0 8px 8px 0;"'),
]

for pattern, repl in replacements:
    body_html = re.sub(pattern, repl, body_html)

# 删除多余的 id 属性，以防微信冲突
body_html = re.sub(r' id="[^"]+"', '', body_html)

# --- 手机端精简与排版适配 ---
# 1. 将所有用于横向并排的 display: flex; (带有 gap 或 space-between) 转为单列纵向排列
def flex_to_column(match):
    style_str = match.group(1)
    if 'gap' in style_str or 'space-between' in style_str:
        style_str = style_str.replace('display: flex;', 'display: flex; flex-direction: column;')
    return style_str
body_html = re.sub(r'(style="[^"]*display:\s*flex;[^"]*")', flex_to_column, body_html)

# 2. 将 flex: 1 替换掉，防止子元素在 column 模式下强行等分或溢出，并增加下边距
body_html = re.sub(r'flex:\s*1;?', 'margin-bottom: 12px;', body_html)

# 3. 将表示横向流程的 ➔ 箭头，转为向下箭头，并加上下居中
body_html = re.sub(r'<div[^>]*>➔</div>', r'<div style="text-align: center; color: #bbb; font-size: 20px; margin: 5px 0;">⬇</div>', body_html)
body_html = body_html.replace('➔', '⬇')

# 4. 优化表格与字号
body_html = re.sub(r'(?<!-)\bwidth:\s*\d+%;?', '', body_html) # 移除固定百分比宽度，避开 max-width
body_html = body_html.replace('font-size: 2.2em;', 'font-size: 1.6em; text-align: center;')
body_html = body_html.replace('font-size: 1.8em;', 'font-size: 1.4em;')
body_html = body_html.replace('font-size: 1.4em;', 'font-size: 1.2em;')
body_html = body_html.replace('padding: 20px;', 'padding: 12px;') # 缩小卡片内边距

# 包装为最终 HTML
final_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>媒小宝公众号图文</title>
</head>
<body style="margin: 0; padding: 0;">
<section style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; padding: 15px; background-color: #FAFAFA; color: #333; line-height: 1.6; font-size: 15px;">
{body_html}
</section>
</body>
</html>
"""

with open(target_file, "w", encoding="utf-8") as f:
    f.write(final_html)

print(f"✅ 已成功生成公众号专用 HTML 文件：{target_file}")
