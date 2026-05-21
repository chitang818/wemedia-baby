"""
百家号插件 JavaScript 脚本
文件路径: src/plugins/pro/baijiahao/scripts.py
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
        var isBjhPage = currentUrl.indexOf('baijiahao.baidu.com') !== -1;
        var isLoginPage = currentUrl.indexOf('passport.baidu.com') !== -1
                       || currentUrl.indexOf('/login') !== -1;

        // 方法1：检测关键 Cookie
        try {
            var cookies = document.cookie.split(';');
            var keyCookieNames = ['BDUSS', 'STOKEN'];
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
            { selector: '.app-header-username, .user-name', description: '用户名' },
            { selector: 'span[class*="username"], span[class*="user-name"]', description: '用户名标签' },
            { selector: 'div[class*="user-info"]', description: '用户信息区域' }
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
            '.app-header-username',
            '.user-name',
            '.header-user-name',
            'span[class*="username"]',
            'span[class*="user-name"]',
            'div[class*="user-info"] span'
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
        var hasBduss = result.cookies.indexOf('BDUSS') !== -1;
        var hasStoken = result.cookies.indexOf('STOKEN') !== -1;
        var hasUserElements = foundElements.length > 0;

        if (username && username.length > 0) {
            result.loggedIn = true;
            result.method = 'username_found';
        } else if (hasBduss && hasStoken && isBjhPage && !isLoginPage) {
            result.loggedIn = true;
            result.method = 'cookie_and_page';
        } else if (hasBduss && hasUserElements) {
            result.loggedIn = true;
            result.method = 'cookie_and_elements';
        }

        result.debug.push('hasBduss: ' + hasBduss);
        result.debug.push('hasStoken: ' + hasStoken);
        result.debug.push('isBjhPage: ' + isBjhPage);
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
