"""
头条号插件 JavaScript 脚本
文件路径: src/plugins/pro/toutiao/scripts.py
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
        var isMpPage = currentUrl.indexOf('mp.toutiao.com') !== -1;
        var isLoginPage = currentUrl.indexOf('/login') !== -1 || currentUrl.indexOf('/auth/') !== -1;

        var hasQrCode = document.querySelector('canvas[class*="qr"], img[class*="qr"], [class*="qrcode"]') !== null;
        if (hasQrCode) {
            isLoginPage = true;
        }

        // 方法1：检测关键 Cookie
        try {
            var cookies = document.cookie.split(';');
            var keyCookieNames = ['sessionid', 'sso_uid_tt', 'ttwid'];
            var foundCookies = [];
            cookies.forEach(function(cookie) {
                var cookieName = cookie.split('=')[0].trim();
                for (var i = 0; i < keyCookieNames.length; i++) {
                    if (cookieName === keyCookieNames[i]) {
                        foundCookies.push(cookieName);
                    }
                }
            });
            result.cookies = foundCookies;
        } catch (e) {}

        // 方法2：检测关键 DOM 元素
        var elementIndicators = [
            { selector: 'div[class*="avatar"], img[class*="avatar"]', description: '用户头像' },
            { selector: 'div[class*="user-info"], div[class*="userInfo"]', description: '用户信息区域' },
            { selector: 'span[class*="nickname"], div[class*="nickname"]', description: '用户昵称' },
            { selector: '.user-name, .account-name', description: '用户名' }
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
        result.indicators = foundElements;

        // 提取用户名
        var username = '';
        var nameSelectors = [
            '.user-name', '.account-name', '.header-user-name',
            'span[class*="nickname"]', 'div[class*="nickname"]',
            'span[class*="name"]'
        ];

        for (var i = 0; i < nameSelectors.length; i++) {
            try {
                var els = document.querySelectorAll(nameSelectors[i]);
                for (var j = 0; j < els.length; j++) {
                    var text = els[j].innerText;
                    if (text) {
                        text = text.trim();
                        if (text.length > 0 && text.length < 30 && text.indexOf('登录') === -1) {
                            username = text;
                            break;
                        }
                    }
                }
                if (username) break;
            } catch (e) {}
        }
        result.username = username;

        // 综合判断
        var hasSessionCookie = result.cookies.indexOf('sessionid') !== -1;
        var hasSsoCookie = result.cookies.indexOf('sso_uid_tt') !== -1;
        var hasUserElements = foundElements.length > 0;

        if (username && username.length > 0) {
            result.loggedIn = true;
            result.method = 'username_found';
        } else if (hasSessionCookie && isMpPage && !isLoginPage) {
            result.loggedIn = true;
            result.method = 'cookie_and_page';
        } else if ((hasSessionCookie || hasSsoCookie) && hasUserElements) {
            result.loggedIn = true;
            result.method = 'cookie_and_elements';
        }

        result.debug.push('hasSessionCookie: ' + hasSessionCookie);
        result.debug.push('hasSsoCookie: ' + hasSsoCookie);
        result.debug.push('isMpPage: ' + isMpPage);
        result.debug.push('isLoginPage: ' + isLoginPage);
        result.debug.push('hasUserElements: ' + hasUserElements);

        return JSON.stringify(result);
    } catch (e) {
        return JSON.stringify({
            loggedIn: false,
            error: e.toString()
        });
    }
})();
"""
