import asyncio
import os
import sys

try:
    # 媒小宝项目基于 patchright，所以使用 patchright 替代原版 playwright
    from patchright.async_api import async_playwright
except ImportError:
    print("[Error] 缺少 patchright 依赖，无法导出 PDF。")
    print("如果您在虚拟环境中，请确认已激活环境。")
    sys.exit(1)

async def export_pdf():
    # 获取项目根目录 (相对于 scripts/maintenance)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    html_path = os.path.join(base_dir, 'docs', '使用说明', 'index.html')
    pdf_path = os.path.join(base_dir, 'docs', '使用说明', '媒小宝使用说明.pdf')
    
    if not os.path.exists(html_path):
        print(f"[Error] 找不到 HTML 文档：{html_path}")
        sys.exit(1)

    print("[Info] 正在启动无头浏览器进行 PDF 导出...")
    try:
        async with async_playwright() as p:
            # 启动 chromium
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # 将本地路径转换为 file:// 协议
            file_url = f"file:///{html_path.replace(os.sep, '/')}"
            print(f"[Info] 正在加载页面: {file_url}")
            await page.goto(file_url, wait_until="networkidle")
            
            print(f"[Info] 正在生成 PDF 样式并保存至: {pdf_path}")
            # 导出 PDF，开启背景打印并设置 A4 大小
            await page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                margin={"top": "1.5cm", "right": "1.5cm", "bottom": "1.5cm", "left": "1.5cm"}
            )
            
            await browser.close()
            print("\n[Success] PDF 导出成功！")
            print(f"👉 文件路径: {pdf_path}")
    except Exception as e:
        print(f"\n[Error] 导出 PDF 失败，发生错误: {e}")

if __name__ == "__main__":
    asyncio.run(export_pdf())
