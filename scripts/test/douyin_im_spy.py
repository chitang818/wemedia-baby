import asyncio
import argparse
import logging
from urllib.parse import urlparse
from patchright.async_api import async_playwright, Request, WebSocket

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger("douyin_im_spy")

# 需要重点监听的 API 路径关键字
TARGET_API_KEYWORDS = ["/im/", "/message/", "/session/", "/msg/"]

async def handle_request(request: Request):
    """拦截并打印关心的 HTTP 请求"""
    url = request.url
    parsed_url = urlparse(url)
    path = parsed_url.path
    
    if any(keyword in path for keyword in TARGET_API_KEYWORDS):
        logger.info(f"[HTTP] 发现目标 API: {request.method} {url}")
        
        # 尝试打印请求参数
        if request.method == "POST":
            post_data = request.post_data
            if post_data:
                logger.info(f"   --> [POST Data]: {post_data}")
                
        # 我们可以尝试挂钩 response 来获取响应内容，但这需要等响应完成
        # 注意: 实际代码中可以使用 page.on("response", ...) 来处理

async def handle_response(response):
    """处理响应，提取敏感数据用于分析"""
    request = response.request
    url = request.url
    parsed_url = urlparse(url)
    path = parsed_url.path
    
    if any(keyword in path for keyword in TARGET_API_KEYWORDS):
        try:
            body = await response.json()
            logger.info(f"[RESPONSE JSON] {path} :\n{body}")
        except Exception:
            logger.debug(f"[RESPONSE] {path} 非 JSON 格式或无法读取")

async def handle_websocket(web_socket: WebSocket):
    """拦截并打印 WebSocket 事件"""
    logger.info(f"[WebSocket] 连接已建立: {web_socket.url}")
    
    web_socket.on("framesent", lambda payload: logger.info(f"[WS] 发送数据: {payload}"))
    web_socket.on("framereceived", lambda payload: logger.info(f"[WS] 接收数据: {payload}"))
    web_socket.on("close", lambda ws: logger.info(f"[WebSocket] 连接已关闭: {ws.url}"))

async def run(user_data_dir: str):
    logger.info("启动 Patchright 浏览器进行抖音私信嗅探...")
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            channel="chrome",  # 建议使用本地 Chrome 防止风控
            args=["--start-maximized"]
        )
        
        page = await browser.new_page()
        
        # 注册监听器
        page.on("request", handle_request)
        page.on("response", handle_response)
        page.on("websocket", handle_websocket)
        
        logger.info("请在打开的浏览器中扫码或手机号登录抖音创作者中心。")
        logger.info("登录后，请导航至【互动管理】->【私信】页面，并尝试点击不同的对话和发送消息。")
        logger.info("脚本将持续打印拦截到的相关网络请求。在控制台按 Ctrl+C 停止。")
        
        await page.goto("https://creator.douyin.com/creator-micro/message")
        
        # 保持运行直到被终止
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到退出信号，正在关闭...")
        finally:
            await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抖音私信接口嗅探工具")
    parser.add_argument("--dir", type=str, default="./debug_douyin_profile", help="用户数据目录，用于持久化登录状态")
    args = parser.parse_args()
    
    asyncio.run(run(args.dir))
