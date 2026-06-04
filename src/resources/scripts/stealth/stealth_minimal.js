// ==========================================================================
// 最小化隐身脚本 (stealth_minimal.js)
// 适用于 strict_real_browser 平台（如小红书）
//
// 设计理念：这些平台对真实浏览器环境依赖强，不做任何硬件/Canvas/Audio 指纹伪造，
// 仅清理 Playwright/CDP 框架留下的自动化痕迹，让浏览器"看起来不是被自动化工具启动的"。
// ==========================================================================

// ========== 1. 隐藏 navigator.webdriver ==========
// Playwright 启动的 Chrome 默认 navigator.webdriver === true
// 这是所有平台检测自动化浏览器的最基础手段
// 使用 toString 伪装为 native code，规避原型链检测
(function () {
  const _getter = function () { return undefined; };
  const _fakeToString = function () { return "function get webdriver() { [native code] }"; };
  Object.defineProperty(_getter, "toString", { value: _fakeToString, writable: false, configurable: false });
  // 同时伪装 _fakeToString.toString，防止二级 toString 检测
  const _metaToString = function () { return "function toString() { [native code] }"; };
  Object.defineProperty(_fakeToString, "toString", { value: _metaToString, writable: false, configurable: false });
  Object.defineProperty(navigator, "webdriver", {
    get: _getter,
    configurable: true,
  });
})();

// ========== 2. 清理自动化框架全局变量 ==========
// 这些变量是各种自动化工具在 window 上留下的痕迹
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

// ========== 3. CDP Runtime Binding 痕迹清理 ==========
// Playwright 通过 Runtime.addBinding 注入的内部绑定
// 尝试删除可能暴露的 cdc_ 前缀属性（ChromeDriver 的遗留命名约定）
try {
  const keys = Object.keys(document);
  for (const key of keys) {
    if (key.startsWith("cdc_") || key.startsWith("__playwright")) {
      try { delete document[key]; } catch (e) {}
    }
  }
} catch (e) {}

// 清理 window 上的 cdc_ 前缀属性
try {
  const windowKeys = Object.keys(window);
  for (const key of windowKeys) {
    if (key.startsWith("cdc_") || key.startsWith("__playwright")) {
      try { delete window[key]; } catch (e) {}
    }
  }
} catch (e) {}

// ========== 4. 确保 chrome 对象完整 ==========
// 某些检测脚本通过 chrome.runtime 的完整性判断是否为真实 Chrome
if (!window.chrome) {
  window.chrome = {
    runtime: {},
    loadTimes: function () {},
    csi: function () {},
    app: {},
  };
} else if (!window.chrome.runtime) {
  window.chrome.runtime = {
    connect: function () {},
    sendMessage: function () {},
    onMessage: {
      addListener: function () {},
      removeListener: function () {},
    },
  };
}

// ========== 5. 页面焦点与可见性伪造 ==========
// 自动化场景下浏览器窗口可能不在前台，document.hasFocus() 返回 false、
// visibilityState 为 hidden，是重要的自动化特征
try {
  Object.defineProperty(document, "hidden", { get: () => false, configurable: true });
  Object.defineProperty(document, "visibilityState", { get: () => "visible", configurable: true });
  document.hasFocus = function () { return true; };
  document.addEventListener("visibilitychange", function (e) {
    e.stopImmediatePropagation();
  }, true);
} catch (e) {}

// ========== 6. Permissions API 基础伪装 ==========
// 正常 Chrome 的 permissions.query 不会抛出异常
// Playwright 可能导致某些权限查询行为异常
if (navigator.permissions && navigator.permissions.query) {
  const _origQuery = navigator.permissions.query.bind(navigator.permissions);
  navigator.permissions.query = function (params) {
    if (params && params.name === "notifications") {
      return Promise.resolve({ state: "prompt" });
    }
    try {
      return _origQuery(params);
    } catch (e) {
      return Promise.resolve({ state: "prompt" });
    }
  };
}

// ========== 7. 插件列表兜底 ==========
// 空插件列表是 Chromium 测试/自动化环境的典型特征
// 仅在插件列表为空时补全，不覆盖已有的真实插件
try {
  if (navigator.plugins && navigator.plugins.length === 0) {
    Object.defineProperty(navigator, "plugins", {
      get: () => [
        { name: "Chrome PDF Plugin", filename: "internal-pdf-viewer" },
        { name: "Chrome PDF Viewer", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai" },
        { name: "Native Client", filename: "internal-nacl-plugin" },
      ],
    });
  }
} catch (e) {}

// ========== 8. mimeTypes 兜底 ==========
// 同理，空 mimeTypes 也是异常特征
try {
  if (navigator.mimeTypes && navigator.mimeTypes.length === 0) {
    Object.defineProperty(navigator, "mimeTypes", {
      get: () => [
        { type: "application/pdf", suffixes: "pdf", description: "Portable Document Format" },
        { type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format" },
      ],
    });
  }
} catch (e) {}
