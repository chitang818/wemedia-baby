"""
小红书插件 JavaScript 脚本
文件路径: src/plugins/pro/xiaohongshu/scripts.py

基于 WeMedia X-Ray DOM 分析报告 (20260306_172008) 实际采集的元素。
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
        var isCreatorPage = currentUrl.indexOf('creator.xiaohongshu.com') !== -1;
        var isLoginPage = currentUrl.indexOf('/login') !== -1;

        // 登录页特征检测
        var hasQrCode = document.querySelector('canvas[class*="qr"], img[class*="qr"], [class*="qrcode"]') !== null;
        if (hasQrCode) {
            isLoginPage = true;
        }

        // 方法1：检测关键 Cookie（web_session 是核心凭证，a1 是设备标识）
        try {
            var cookies = document.cookie.split(';');
            var keyCookieNames = ['web_session', 'a1', 'webId', 'x-user-id'];
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

        // 方法2：检测关键 DOM 元素（来自 X-Ray 实际采集）
        var elementIndicators = [
            { selector: 'img.user_avatar', description: '用户头像' },
            { selector: 'div.avatar', description: '头像容器' },
            { selector: 'div.publish-video', description: '发布按钮区域' },
            { selector: 'span.d-menu-item__title', description: '侧边栏菜单' },
            { selector: 'div.d-topbar-title', description: '顶部栏' }
        ];

        var foundElements = [];
        elementIndicators.forEach(function(indicator) {
            try {
                var element = document.querySelector(indicator.selector);
                if (element) {
                    foundElements.push({
                        selector: indicator.selector,
                        description: indicator.description,
                        found: true
                    });
                }
            } catch (e) {}
        });
        result.indicators = foundElements;

        // 提取用户名
        var username = '';

        // 1. 从 div.name 提取（但需排除 "创作服务平台"）
        try {
            var nameEls = document.querySelectorAll('div.name');
            for (var i = 0; i < nameEls.length; i++) {
                var text = nameEls[i].innerText;
                if (text) {
                    text = text.trim();
                    if (text.length > 0 && text.length < 30
                        && text.indexOf('创作服务平台') === -1
                        && text.indexOf('登录') === -1
                        && text.indexOf('首页') === -1) {
                        username = text;
                        break;
                    }
                }
            }
        } catch (e) {}

        // 2. 从 div.others.description-text 提取小红书号作为兜底
        if (!username) {
            try {
                var descEl = document.querySelector('div.others.description-text');
                if (descEl) {
                    var descText = descEl.innerText;
                    var match = descText.match(/小红书账号[:：]\\s*(\\S+)/);
                    if (match) {
                        username = '小红书用户_' + match[1].slice(-4);
                    }
                }
            } catch (e) {}
        }

        // 3. 从 Vue 实例或全局变量兜底
        if (!username) {
            try {
                var appEl = document.querySelector('#app');
                if (appEl && appEl.__vue_app__) {
                    var state = appEl.__vue_app__.config.globalProperties;
                    if (state && state.$store && state.$store.state) {
                        var s = state.$store.state;
                        if (s.user && s.user.nickname) {
                            username = s.user.nickname;
                        }
                    }
                }
            } catch (e) {}
        }

        result.username = username;

        // 综合判断
        var hasSessionCookie = result.cookies.indexOf('web_session') !== -1;
        var hasUserElements = foundElements.length > 0;

        if (username && username.length > 0) {
            result.loggedIn = true;
            result.method = 'username_found';
        } else if (hasSessionCookie && isCreatorPage && !isLoginPage) {
            result.loggedIn = true;
            result.method = 'cookie_and_page';
        } else if (hasSessionCookie && hasUserElements) {
            result.loggedIn = true;
            result.method = 'cookie_and_elements';
        }

        result.debug.push('hasSessionCookie: ' + hasSessionCookie);
        result.debug.push('isCreatorPage: ' + isCreatorPage);
        result.debug.push('isLoginPage: ' + isLoginPage);
        result.debug.push('hasUserElements: ' + hasUserElements);
        result.debug.push('foundElementsCount: ' + foundElements.length);

        return JSON.stringify(result);
    } catch (e) {
        return JSON.stringify({
            loggedIn: false,
            error: e.toString()
        });
    }
})();
"""
