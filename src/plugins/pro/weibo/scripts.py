"""
新浪微博插件 JavaScript 脚本
文件路径: src/plugins/pro/weibo/scripts.py
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
        var isWeiboPage = currentUrl.indexOf('weibo.com') !== -1;
        var isLoginPage = currentUrl.indexOf('passport.weibo') !== -1
                       || currentUrl.indexOf('/login') !== -1
                       || currentUrl.indexOf('/sso/signin') !== -1;

        // 方法1：检测关键 Cookie
        try {
            var cookies = document.cookie.split(';');
            var keyCookieNames = ['SUB', 'SUBP', 'XSRF-TOKEN', 'login_sid_t'];
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

        // 方法2：检测关键 DOM 元素（微博登录后的用户相关元素）
        var elementIndicators = [
            { selector: 'img[class*="avatar"], div[class*="avatar"] img', description: '用户头像' },
            { selector: 'a[class*="name"] span, span[class*="screen_name"]', description: '用户昵称' },
            { selector: 'div[class*="Nav_user"], div[class*="woo-box"] a[href*="/profile"]', description: '用户导航' },
            { selector: 'a[href*="/u/"] span', description: '用户链接' }
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
            'a[class*="name"] span',
            'span[class*="screen_name"]',
            'a[class*="ALink_none"] span',
            'div[class*="Nav_user"] span',
            'a[href*="/profile"] span',
            'span[class*="userName"]'
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
        var hasSUB = result.cookies.indexOf('SUB') !== -1;
        var hasSUBP = result.cookies.indexOf('SUBP') !== -1;
        var hasUserElements = foundElements.length > 0;

        if (username && username.length > 0) {
            result.loggedIn = true;
            result.method = 'username_found';
        } else if (hasSUB && hasSUBP && isWeiboPage && !isLoginPage) {
            result.loggedIn = true;
            result.method = 'cookie_and_page';
        } else if (hasSUB && hasUserElements) {
            result.loggedIn = true;
            result.method = 'cookie_and_elements';
        }

        result.debug.push('hasSUB: ' + hasSUB);
        result.debug.push('hasSUBP: ' + hasSUBP);
        result.debug.push('isWeiboPage: ' + isWeiboPage);
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
