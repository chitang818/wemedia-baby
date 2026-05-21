"""
多多视频插件 JavaScript 脚本
文件路径: src/plugins/pro/duoduoshipin/scripts.py
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
        var isCreatorPage = currentUrl.indexOf('live.pinduoduo.com/creator') !== -1;
        var isLoginPage = currentUrl.indexOf('/login') !== -1;

        // 方法1：检测关键 Cookie
        try {
            var cookies = document.cookie.split(';');
            var keyCookieNames = ['PASS_ID', 'PDDAccessToken', 'pdd_user_id'];
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
            { selector: 'img[class*="avatar"], div[class*="avatar"] img', description: '用户头像' },
            { selector: 'div[class*="user-name"], span[class*="user-name"]', description: '用户名' },
            { selector: 'div[class*="nickname"], span[class*="nickname"]', description: '昵称' }
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
            'div[class*="user-name"]',
            'span[class*="user-name"]',
            'div[class*="nickname"]',
            'span[class*="nickname"]',
            'div[class*="username"]',
            'div[class*="header"] span[class*="name"]'
        ];

        for (var i = 0; i < nameSelectors.length; i++) {
            try {
                var els = document.querySelectorAll(nameSelectors[i]);
                for (var j = 0; j < els.length; j++) {
                    var text = els[j].innerText;
                    if (text) {
                        text = text.trim();
                        if (text.length > 0 && text.length < 30
                            && text.indexOf('登录') === -1
                            && text.indexOf('注册') === -1) {
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
        var hasPassId = result.cookies.indexOf('PASS_ID') !== -1;
        var hasAccessToken = result.cookies.indexOf('PDDAccessToken') !== -1;
        var hasUserElements = foundElements.length > 0;

        if (username && username.length > 0) {
            result.loggedIn = true;
            result.method = 'username_found';
        } else if (hasPassId && isCreatorPage && !isLoginPage) {
            result.loggedIn = true;
            result.method = 'cookie_and_page';
        } else if (hasAccessToken && hasUserElements) {
            result.loggedIn = true;
            result.method = 'cookie_and_elements';
        }

        result.debug.push('hasPassId: ' + hasPassId);
        result.debug.push('hasAccessToken: ' + hasAccessToken);
        result.debug.push('isCreatorPage: ' + isCreatorPage);
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
