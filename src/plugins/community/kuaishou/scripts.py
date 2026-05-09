"""
Kuaishou Plugin Scripts
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
        var isCreatorPage = currentUrl.indexOf('cp.kuaishou.com') !== -1;
        var isLoginPage = currentUrl.indexOf('/login') !== -1 || currentUrl.indexOf('/signin') !== -1;
        
        // 检测登录页面的特征
        var hasQrCode = document.querySelector('canvas[class*="qr"], img[class*="qr"], [class*="二维码"]') !== null;
        var hasScanLogin = document.body.innerText.indexOf('扫码登录') !== -1;
        var isLoginPageElement = hasQrCode || hasScanLogin;
        
        if (isLoginPageElement) {
            isLoginPage = true;
        }
        
        // 方法1: 检测关键元素
        var elementIndicators = [
            { selector: 'div[class*="avatar"], img[class*="avatar"]', description: '用户头像' },
            { selector: 'div[class*="user-info"], div[class*="userInfo"]', description: '用户信息区域' },
            { selector: 'span[class*="nickname"], div[class*="nickname"]', description: '用户昵称' },
            { selector: 'button[class*="publish"], [class*="发布"]', description: '发布按钮' }
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
            var keyCookieNames = [
                'kuaishou.web.cp.api_st', 'kuaishou.web.cp.api_ph',
                'userId', 'bUserId', 'kwfv1', 'did'
            ];
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
        var globalVars = ['__INITIAL_STATE__', '__USER_INFO__', '__PRELOADED_STATE__'];
        for (var i = 0; i < globalVars.length; i++) {
            try {
                if (window[globalVars[i]] && window[globalVars[i]].user && window[globalVars[i]].user.name) {
                    username = window[globalVars[i]].user.name;
                    break;
                }
            } catch(e) {}
        }
        
        // 2. 从DOM元素
        if (!username) {
            var nameSelectors = [
                '.user-name',
                '.header-user-name', 
                'div[class*="UserInfo-module_name"]',
                '.user-info-name',
                '.avatar-name',
                'div[class*="name"]'
            ];
            
            for (var i = 0; i < nameSelectors.length; i++) {
                var el = document.querySelector(nameSelectors[i]);
                if (el) {
                    var text = el.innerText.trim();
                    if (text && text.length > 0 && text.length < 30 && text.indexOf('登录') === -1) {
                        username = text;
                        break;
                    }
                }
            }
        }
        
        result.username = username;
        
        // 综合判断：必须同时满足 [非登录页] + ([关键Cookie] 或 [用户名存在])
        var hasAuthCookie = result.cookies.indexOf('kuaishou.web.cp.api_st') !== -1 || result.cookies.indexOf('kuaishou.web.cp.api_ph') !== -1;
        var hasIdentity = username && username.length > 0;
        
        if (!isLoginPage && !isLoginPageElement) {
            if (hasAuthCookie && hasIdentity) {
                result.loggedIn = true;
            }
        }
        
        // 兜底校验：如果发现了明确的“退出”字样且有用户名
        if (!result.loggedIn && hasIdentity && document.body.innerText.indexOf('退出') !== -1) {
            result.loggedIn = true;
        }
        
        return JSON.stringify(result);
    } catch (e) {
        return JSON.stringify({
            loggedIn: false,
            error: e.toString()
        });
    }
})();
"""
