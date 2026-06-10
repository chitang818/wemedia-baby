// ==========================================================================
// 最小化隐身脚本 (stealth_minimal.js)
// 适用于：
//   1. strict_real_browser 平台（如小红书）
//   2. real_browser 默认模式（注入基础防护）
//
// 设计理念：不做硬件/Canvas/Audio 等重型指纹伪造，
// 仅清理 Playwright/CDP 框架自动化痕迹，并修复最关键的 JS 检测点。
// ==========================================================================

// ========== 0. native code toString 工具函数 ==========
// 与 stealth.js 保持同等防护等级：所有注入 getter 必须伪装 toString
(function () {
  window.__makeNativeGetter = function (propName, value) {
    var getter = typeof value === 'function' ? value : function () { return value; };
    var fakeToString = function () { return 'function get ' + propName + '() { [native code] }'; };
    var metaToString = function () { return 'function toString() { [native code] }'; };
    try {
      Object.defineProperty(fakeToString, 'toString', { value: metaToString, writable: false, configurable: false });
      Object.defineProperty(getter, 'toString', { value: fakeToString, writable: false, configurable: false });
    } catch (e) {}
    return getter;
  };
  window.__makeNativeFn = function (methodName, fn) {
    var fakeToString = function () { return 'function ' + methodName + '() { [native code] }'; };
    var metaToString = function () { return 'function toString() { [native code] }'; };
    try {
      Object.defineProperty(fakeToString, 'toString', { value: metaToString, writable: false, configurable: false });
      Object.defineProperty(fn, 'toString', { value: fakeToString, writable: false, configurable: false });
    } catch (e) {}
    return fn;
  };
})();

var _nativeGetter = window.__makeNativeGetter;
var _nativeFn = window.__makeNativeFn;

// ========== 1. 隐藏 navigator.webdriver ==========
// Playwright 启动的 Chrome 默认 navigator.webdriver === true
// 使用 toString 伪装为 native code，规避「toString 检测」
(function () {
  var _getter = _nativeGetter('webdriver', undefined);
  Object.defineProperty(navigator, 'webdriver', {
    get: _getter,
    configurable: true,
  });
})();

// ========== 2. 清理自动化框架全局变量 ==========
delete window.__playwright;
delete window.__pw_target;
delete window.__puppeteer;
delete window.__selenium;
delete window.callPhantom;
delete window._phantom;
delete window.__nightmare;
delete window.__fxdriver_unwrapped;
delete window.__webdriver_unwrapped;
delete window.__driver_evaluate;
delete window.__webdriver_evaluate;
delete window.__selenium_evaluate;
delete window.__fxdriver_evaluate;
delete window.__driver_unwrapped;
delete window.__webdriver_script_function;
delete window.__webdriver_script_func;
delete window.__webdriver_script_fn;

// ========== 3. CDP cdc_ 前缀属性清理 ==========
try {
  ['window', 'document'].forEach(function (target) {
    var obj = target === 'window' ? window : document;
    try {
      var keys = Object.getOwnPropertyNames(obj);
      for (var i = 0; i < keys.length; i++) {
        if (keys[i].startsWith('cdc_') || keys[i].startsWith('__playwright') || keys[i].startsWith('__pw_')) {
          try { delete obj[keys[i]]; } catch (e) {}
        }
      }
    } catch (e) {}
  });
} catch (e) {}

// ========== 4. 确保 chrome 对象完整 ==========
try {
  if (!window.chrome) {
    window.chrome = {
      runtime: {
        connect: _nativeFn('connect', function () {}),
        sendMessage: _nativeFn('sendMessage', function () {}),
        onMessage: { addListener: function () {}, removeListener: function () {} },
        id: undefined,
      },
      loadTimes: _nativeFn('loadTimes', function () {}),
      csi: _nativeFn('csi', function () {}),
      app: {},
    };
  } else if (!window.chrome.runtime) {
    window.chrome.runtime = {
      connect: _nativeFn('connect', function () {}),
      sendMessage: _nativeFn('sendMessage', function () {}),
      onMessage: { addListener: function () {}, removeListener: function () {} },
    };
  }
} catch (e) {}

// ========== 5. 页面焦点与可见性伪造 ==========
// 自动化场景下浏览器窗口可能不在前台，是重要的自动化特征
try {
  Object.defineProperty(document, 'hidden', { get: _nativeGetter('hidden', false), configurable: true });
  Object.defineProperty(document, 'visibilityState', { get: _nativeGetter('visibilityState', 'visible'), configurable: true });
  document.hasFocus = _nativeFn('hasFocus', function () { return true; });
  document.addEventListener('visibilitychange', function (e) { e.stopImmediatePropagation(); }, true);
} catch (e) {}

// ========== 6. Permissions API 基础伪装 ==========
try {
  if (navigator.permissions && navigator.permissions.query) {
    var _origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = _nativeFn('query', function (params) {
      if (params && params.name === 'notifications') {
        return Promise.resolve({ state: 'granted' });
      }
      try { return _origQuery(params); } catch (e) { return Promise.resolve({ state: 'prompt' }); }
    });
  }
} catch (e) {}

// Notification.permission 与 permissions API 一致
try {
  if (typeof Notification !== 'undefined' && Notification.permission !== 'granted') {
    Object.defineProperty(Notification, 'permission', {
      get: _nativeGetter('permission', 'granted'),
      configurable: true,
    });
  }
} catch (e) {}

// ========== 7. 插件列表兜底 ==========
// 空插件列表是 Chromium 测试/自动化环境的典型特征
try {
  if (navigator.plugins && navigator.plugins.length === 0) {
    Object.defineProperty(navigator, 'plugins', {
      get: _nativeGetter('plugins', [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
      ]),
      configurable: true,
    });
  }
} catch (e) {}

// ========== 8. mimeTypes 兜底 ==========
try {
  if (navigator.mimeTypes && navigator.mimeTypes.length === 0) {
    Object.defineProperty(navigator, 'mimeTypes', {
      get: _nativeGetter('mimeTypes', [
        { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
        { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' },
      ]),
      configurable: true,
    });
  }
} catch (e) {}

// ========== 9. performance.now() 时序微抖动 ==========
try {
  var _origPerfNow = performance.now.bind(performance);
  var _perfOffset = 0;
  performance.now = _nativeFn('now', function () {
    _perfOffset += (Math.random() - 0.5) * 0.16;
    if (_perfOffset > 2) _perfOffset = 2;
    if (_perfOffset < -2) _perfOffset = -2;
    return _origPerfNow() + _perfOffset;
  });
} catch (e) {}

// ========== 10. Headless outerWidth/outerHeight 兜底 ==========
try {
  if (window.outerWidth === 0) {
    Object.defineProperty(window, 'outerWidth', { get: _nativeGetter('outerWidth', function () { return window.innerWidth; }), configurable: true });
  }
  if (window.outerHeight === 0) {
    Object.defineProperty(window, 'outerHeight', { get: _nativeGetter('outerHeight', function () { return window.innerHeight + 85; }), configurable: true });
  }
} catch (e) {}

// ========== 11. Error.stack 路径清理 ==========
try {
  var _origPrepare = Error.prepareStackTrace;
  if (_origPrepare) {
    Error.prepareStackTrace = _nativeFn('prepareStackTrace', function (err, stack) {
      var result = _origPrepare(err, stack);
      if (typeof result === 'string') {
        return result.replace(/\s+at.*patchright.*/g, '').replace(/\s+at.*playwright.*/gi, '');
      }
      return result;
    });
  }
} catch (e) {}
