"""
哔哩哔哩插件 JavaScript 脚本
文件路径: src/plugins/pro/bilibili/scripts.py
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
        var isMemberPage = currentUrl.indexOf('member.bilibili.com') !== -1;
        var isLoginPage = currentUrl.indexOf('passport.bilibili.com') !== -1
                       || currentUrl.indexOf('/login') !== -1;

        // 方法1：检测关键 Cookie
        try {
            var cookies = document.cookie.split(';');
            var keyCookieNames = ['SESSDATA', 'bili_jct', 'DedeUserID'];
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
            { selector: 'span[class*="nickname"], div[class*="nickname"]', description: '用户昵称' },
            { selector: 'div[class*="uname"]', description: '用户名' },
            { selector: '.header-upload-entry .nickname', description: '上传入口昵称' }
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
            '.header-upload-entry .nickname',
            '.mini-avatar .nickname',
            'div[class*="uname"]',
            'span[class*="nickname"]',
            'a[class*="header-entry"] .name'
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
        var hasSessdata = result.cookies.indexOf('SESSDATA') !== -1;
        var hasUserElements = foundElements.length > 0;

        if (username && username.length > 0) {
            result.loggedIn = true;
            result.method = 'username_found';
        } else if (hasSessdata && isMemberPage && !isLoginPage) {
            result.loggedIn = true;
            result.method = 'cookie_and_page';
        } else if (hasSessdata && hasUserElements) {
            result.loggedIn = true;
            result.method = 'cookie_and_elements';
        }

        result.debug.push('hasSessdata: ' + hasSessdata);
        result.debug.push('isMemberPage: ' + isMemberPage);
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
