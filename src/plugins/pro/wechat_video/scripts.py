"""
视频号插件 — 注入浏览器的 JavaScript 检测脚本
文件路径: src/plugins/pro/wechat_video/scripts.py

通过注入 JS 脚本检测登录状态和提取用户信息，
比纯 Cookie 判断更准确（可检测到前端已渲染的登录态元素）。
"""

# 登录状态检测脚本（在浏览器端执行）
LOGIN_DETECTION_SCRIPT = """
(function() {

    var result = {
        loggedIn: false,
        username: null,
        avatar: null,
        userId: null,
        debug: ''
    };
    
    try {
        // 显式登录页（扫码等）：避免与首页营销区/占位图上的 avatar 等节点混淆
        var href = (typeof location !== 'undefined' && location.href) ? location.href : '';
        var path = (typeof location !== 'undefined' && location.pathname) ? location.pathname : '';
        var pl = (path || '').toLowerCase();
        if (href.indexOf('login.html') >= 0 || pl === '/login' || pl.indexOf('/login/') === 0
                || (pl.length >= 6 && pl.slice(-6) === '/login')) {
            return JSON.stringify(result);
        }

        // 登录状态指示器：检测页面中是否存在用户信息相关元素
        var indicators = [
            '.user-info', '.userInfo', '.finder-info', '.header-info',
            '.account-info',
            '.avatar', '.user-avatar', '.finder-avatar', 'img[src*="head"]',
            '.nickname', '.finder-nickname', '.header-name', '.account-name',
            '.profile-info', '.user-center', '.user-name'
        ];
        
        for (var i = 0; i < indicators.length; i++) {
            if (document.querySelector(indicators[i])) {
                result.loggedIn = true;
                result.debug += "Found indicator: " + indicators[i] + "; ";
                break;
            }
        }
        
        // 已登录时提取用户信息
        if (result.loggedIn) {
            // 优先从 localStorage 读取昵称（视频号把用户名存在 finder_username，比 DOM 节点更早、更稳定）
            try {
                var lsName = localStorage.getItem('finder_username');
                if (lsName && lsName.trim()) {
                    // finder_username 可能是 base64 或 JSON 编码，尝试解码
                    var decoded = lsName.trim();
                    try { decoded = atob(decoded); } catch(e2) {}
                    try {
                        var parsed = JSON.parse(decoded);
                        if (typeof parsed === 'string' && parsed.trim()) decoded = parsed.trim();
                        else if (parsed && parsed.nickname) decoded = parsed.nickname;
                        else if (parsed && parsed.name) decoded = parsed.name;
                    } catch(e3) {}
                    if (decoded && decoded.trim() && decoded.trim() !== 'undefined') {
                        var finalStr = decoded.trim();
                        // 过滤掉微信最新的 finder_username 哈希前缀 (例如 v2_06000...)
                        if (finalStr.indexOf('v1_') !== 0 && finalStr.indexOf('v2_') !== 0 && finalStr.length <= 50) {
                            result.username = finalStr;
                            result.debug += "Found nickname via localStorage.finder_username; ";
                        } else {
                            result.debug += "Skipped localStorage.finder_username due to hash format; ";
                        }
                    }
                }
            } catch(lsErr) {}

            // 若 localStorage 未取到，回退 DOM 选择器
            if (!result.username) {
                var nicknameSelectors = [
                    '.finder-nickname',
                    '.header-name',
                    '.account-name',
                    '.account-info .nickname',
                    '.account-info [class*="nick"]',
                    '.account-info',
                    '.user-name',
                    '.nickname',
                    '[class*="nickname"]',
                    '[class*="nickName"]',
                    '.finder-info span'
                ];
                for (var i = 0; i < nicknameSelectors.length; i++) {
                    var el = document.querySelector(nicknameSelectors[i]);
                    if (el) {
                        var text = el.innerText || el.textContent;
                        if (text && text.trim()) {
                            var tStr = text.trim();
                            if (tStr.indexOf('v1_') !== 0 && tStr.indexOf('v2_') !== 0 && tStr.length <= 50) {
                                result.username = tStr;
                                result.debug += "Found nickname via: " + nicknameSelectors[i] + "; ";
                                break;
                            }
                        }
                    }
                }
            }
            
            // 提取头像
            var avatarSelectors = [
                '.finder-avatar img', 
                '.header-avatar img', 
                '.user-avatar img', 
                'img[src*="head"]', 
                '.avatar img', 
                '[class*="avatar"] img',
                'img[class*="avatar"]'
            ];
            
            for (var i = 0; i < avatarSelectors.length; i++) {
                var el = document.querySelector(avatarSelectors[i]);
                if (el) {
                    if (el.tagName === 'IMG' && el.src) {
                        result.avatar = el.src;
                        break;
                    }
                    // 兜底：背景图方式
                    var style = window.getComputedStyle(el);
                    if (style.backgroundImage && style.backgroundImage !== 'none') {
                        result.avatar = style.backgroundImage.slice(4, -1).replace(/"/g, "");
                        break;
                    }
                }
            }
        }
        
    } catch (e) {
        console.error('Login detection script error:', e);
        result.debug += "Error: " + e.message;
    }
    
    return JSON.stringify(result);
})();
"""
