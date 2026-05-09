"""
Douyin Plugin Scripts
"""

LOGIN_DETECTION_SCRIPT = """
(function() {
    try {
        var result = {
            loggedIn: false,
            method: 'unknown',
            indicators: [],
            cookies: [],
            username: '',
            url: window.location.href,
            details: {},
            debug: []
        };
        
        var currentUrl = window.location.href;
        var isCreatorPage = currentUrl.indexOf('creator.douyin.com') !== -1;
        var isLoginPage = currentUrl.indexOf('/login') !== -1 || currentUrl.indexOf('/signin') !== -1;
        
        // 检测登录页面的特征
        var hasQrCode = document.querySelector('canvas[class*="qr"], img[class*="qr"], [class*="二维码"]') !== null;
        var hasScanLogin = document.body.innerText.indexOf('扫码登录') !== -1 || 
                           document.body.innerText.indexOf('我是创作者') !== -1;
        var isLoginPageElement = hasQrCode || hasScanLogin;
        
        if (isLoginPageElement) {
            isLoginPage = true;
        }
        
        // 方法1: 检测关键元素
        var elementIndicators = [
            { selector: 'div[class*="avatar"], img[class*="avatar"], [class*="Avatar"]', description: '用户头像' },
            { selector: 'div[class*="user-info"], div[class*="userInfo"]', description: '用户信息区域' },
            { selector: 'span[class*="nickname"], div[class*="nickname"]', description: '用户昵称' },
            { selector: 'button[class*="publish"], button[class*="Publish"], [class*="发布"]', description: '发布按钮' }
        ];
        
        var foundElements = [];
        elementIndicators.forEach(function(indicator) {
            try {
                var selectors = indicator.selector.split(',');
                for (var i = 0; i < selectors.length; i++) {
                    var element = document.querySelector(selectors[i].trim());
                    if (element) {
                        foundElements.push({
                            selector: selectors[i].trim(),
                            description: indicator.description,
                            found: true
                        });
                        break;
                    }
                }
            } catch (e) {}
        });
        
        // 方法2: 检测Cookie
        try {
            var cookies = document.cookie.split(';');
            var keyCookieNames = ['sessionid', 'sessionid_ss'];
            var foundCookies = [];
            cookies.forEach(function(cookie) {
                var cookieName = cookie.split('=')[0].trim();
                for (var i = 0; i < keyCookieNames.length; i++) {
                    if (cookieName.indexOf(keyCookieNames[i]) !== -1) {
                        foundCookies.push(cookieName);
                    }
                }
            });
            result.cookies = foundCookies;
        } catch (e) {}
        
        // 提取用户名
        var username = '';
        
        // 1. 从全局变量
        var globalVars = ['__INITIAL_STATE__', '__USER_INFO__', 'USER_INFO', 'userInfo'];
        for (var i = 0; i < globalVars.length; i++) {
            if (window[globalVars[i]] && window[globalVars[i]].nickname) {
                username = window[globalVars[i]].nickname;
                break;
            }
        }
        
        // 2. 从DOM元素
        if (!username) {
            var nameSelectors = [
                'div.name-_lSSDc',
                'div[class^="name-"]',
                '.user-info .name',
                '[class*="name-_lSSDc"]',
                '.nickname',
                'div[class*="user-name"]'
            ];
            
            for (var i = 0; i < nameSelectors.length; i++) {
                var els = document.querySelectorAll(nameSelectors[i]);
                for (var j = 0; j < els.length; j++) {
                    var el = els[j];
                    if (el) {
                        var text = el.innerText;
                        if (text) {
                            text = text.trim();
                            if (text.indexOf('\n') !== -1) {
                                text = text.split('\n')[0].trim();
                            }
                            if (text.length > 0 && text.length < 30 && text.indexOf('登录') === -1) {
                                username = text;
                                break;
                            }
                        }
                    }
                }
                if (username) {
                    break;
                }
            }
        }
        
        result.username = username;
        
        // 综合判断
        // 必须找到关键的 Session Cookie
        var hasSessionCookie = false;
        for (var i = 0; i < result.cookies.length; i++) {
            if (result.cookies[i] === 'sessionid' || result.cookies[i] === 'sessionid_ss') {
                hasSessionCookie = true;
                break;
            }
        }
        
        // 检查是否在管理页面（强特征）
        var path = window.location.pathname;
        var isManagePage = path.indexOf('/manage/') !== -1 || 
                           path.indexOf('/content/') !== -1 || 
                           path.indexOf('/home') !== -1 ||
                           path.indexOf('/creator/') !== -1;
        
        // 排除掉纯 /creator/ 根路径（如果是落地页）
        // 但通常 creator.douyin.com 会重定向
        
        // 判定逻辑
        if (username && username.length > 0) {
            // 提取到了用户名，肯定已登录
            result.loggedIn = true;
        } else if (hasSessionCookie && isManagePage && !isLoginPage) {
            // 有Session且在管理页且不在登录页
            result.loggedIn = true;
        }
        
        // 记录调试信息
        result.debug.push('hasSessionCookie: ' + hasSessionCookie);
        result.debug.push('isManagePage: ' + isManagePage);
        result.debug.push('path: ' + path);
        
        return JSON.stringify(result);
    } catch (e) {
        return JSON.stringify({
            loggedIn: false,
            error: e.toString()
        });
    }
})();
"""
