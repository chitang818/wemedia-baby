// ==========================================================================
// WeMediaBaby stealth.js - 全量浏览器指纹与自动化痕迹防护脚本
// 注意：所有 __PLACEHOLDER__ 变量在注入前由 Python 替换为真实值
// ==========================================================================

// ========== 0. 工具函数：native code toString 伪装 ==========
// 检测原理：Object.defineProperty 注入的 getter，调用 toString() 会返回
// "function () { return xxx; }" 而非 "function get xxx() { [native code] }"
// 平台据此识别 stealth 注入，必须对所有 getter 统一处理。
(function () {
  // 缓存原生 Function.prototype.toString，防止被后续代码覆盖
  const _nativeToString = Function.prototype.toString;

  /**
   * 创建一个 toString 返回 [native code] 格式的 getter 函数
   * @param {string} propName - 属性名（如 "hardwareConcurrency"）
   * @param {*} value - getter 返回值（可为常量或函数）
   * @returns {Function} - 可直接传给 Object.defineProperty 的 getter
   */
  window.__makeNativeGetter = function (propName, value) {
    const getter = typeof value === 'function' ? value : function () { return value; };
    const fakeToString = function () {
      return 'function get ' + propName + '() { [native code] }';
    };
    // 二级保护：fakeToString 本身的 toString 也伪装
    const metaToString = function () { return 'function toString() { [native code] }'; };
    try {
      Object.defineProperty(fakeToString, 'toString', { value: metaToString, writable: false, configurable: false });
      Object.defineProperty(getter, 'toString', { value: fakeToString, writable: false, configurable: false });
    } catch (e) {}
    return getter;
  };

  /**
   * 创建一个 toString 返回 [native code] 的普通方法（非 getter）
   * @param {string} methodName - 方法名
   * @param {Function} fn - 实际方法
   */
  window.__makeNativeFn = function (methodName, fn) {
    const fakeToString = function () {
      return 'function ' + methodName + '() { [native code] }';
    };
    const metaToString = function () { return 'function toString() { [native code] }'; };
    try {
      Object.defineProperty(fakeToString, 'toString', { value: metaToString, writable: false, configurable: false });
      Object.defineProperty(fn, 'toString', { value: fakeToString, writable: false, configurable: false });
    } catch (e) {}
    return fn;
  };
})();

const _nativeGetter = window.__makeNativeGetter;
const _nativeFn = window.__makeNativeFn;

// ========== 1. CDP / 自动化框架痕迹清理 ==========
// 必须最先执行，防止后续脚本引用这些属性
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

// 清理 cdc_ 前缀属性（ChromeDriver 遗留命名约定）
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

// ========== 2. 硬件参数伪造（navigator） ==========
try {
  Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: _nativeGetter('hardwareConcurrency', __HARDWARE_CONCURRENCY__),
    configurable: true,
  });
} catch (e) {}

try {
  Object.defineProperty(navigator, 'deviceMemory', {
    get: _nativeGetter('deviceMemory', __DEVICE_MEMORY__),
    configurable: true,
  });
} catch (e) {}

// ========== 3. Screen 屏幕指纹伪造 ==========
try {
  Object.defineProperty(screen, 'width', { get: _nativeGetter('width', __SCREEN_WIDTH__), configurable: true });
  Object.defineProperty(screen, 'height', { get: _nativeGetter('height', __SCREEN_HEIGHT__), configurable: true });
  Object.defineProperty(screen, 'availWidth', { get: _nativeGetter('availWidth', __SCREEN_AVAIL_WIDTH__), configurable: true });
  Object.defineProperty(screen, 'availHeight', { get: _nativeGetter('availHeight', __SCREEN_AVAIL_HEIGHT__), configurable: true });
  Object.defineProperty(screen, 'colorDepth', { get: _nativeGetter('colorDepth', __SCREEN_COLOR_DEPTH__), configurable: true });
  Object.defineProperty(screen, 'pixelDepth', { get: _nativeGetter('pixelDepth', __SCREEN_PIXEL_DEPTH__), configurable: true });
} catch (e) {}

// ========== 4. WebGL 厂商与渲染器伪造 ==========
try {
  const _origGetParam = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = _nativeFn('getParameter', function (parameter) {
    if (parameter === 37445) return '__WEBGL_VENDOR__';   // UNMASKED_VENDOR_WEBGL
    if (parameter === 37446) return '__WEBGL_RENDERER__'; // UNMASKED_RENDERER_WEBGL
    return _origGetParam.apply(this, arguments);
  });
} catch (e) {}

try {
  if (typeof WebGL2RenderingContext !== 'undefined') {
    const _origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = _nativeFn('getParameter', function (parameter) {
      if (parameter === 37445) return '__WEBGL_VENDOR__';
      if (parameter === 37446) return '__WEBGL_RENDERER__';
      return _origGetParam2.apply(this, arguments);
    });
  }
} catch (e) {}

// ========== 5. Navigator 扩展属性伪造 ==========
try {
  Object.defineProperty(navigator, 'platform', { get: _nativeGetter('platform', '__PLATFORM__'), configurable: true });
  Object.defineProperty(navigator, 'maxTouchPoints', { get: _nativeGetter('maxTouchPoints', __MAX_TOUCH_POINTS__), configurable: true });
  Object.defineProperty(navigator, 'vendor', { get: _nativeGetter('vendor', '__VENDOR__'), configurable: true });
  Object.defineProperty(navigator, 'vendorSub', { get: _nativeGetter('vendorSub', '__VENDOR_SUB__'), configurable: true });
  Object.defineProperty(navigator, 'productSub', { get: _nativeGetter('productSub', '__PRODUCT_SUB__'), configurable: true });
} catch (e) {}

// doNotTrack 兜底
try {
  if (typeof navigator.doNotTrack === 'undefined') {
    Object.defineProperty(navigator, 'doNotTrack', { get: _nativeGetter('doNotTrack', null), configurable: true });
  }
} catch (e) {}

// ========== 6. 隐藏 navigator.webdriver ==========
// 原型链保护：toString 伪装为 native code（最成熟的检测手段）
(function () {
  const _getter = _nativeGetter('webdriver', undefined);
  Object.defineProperty(navigator, 'webdriver', {
    get: _getter,
    configurable: true,
  });
})();

// ========== 7. 伪造插件列表 ==========
// 插件名/deviceId 均来自账号固定的随机种子，多账号不完全相同
try {
  Object.defineProperty(navigator, 'plugins', {
    get: _nativeGetter('plugins', [
      { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
      { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
      { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
    ]),
    configurable: true,
  });
} catch (e) {}

// ========== 8. 伪造 mimeTypes ==========
try {
  Object.defineProperty(navigator, 'mimeTypes', {
    get: _nativeGetter('mimeTypes', [
      { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
      { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' },
    ]),
    configurable: true,
  });
} catch (e) {}

// ========== 9. 伪造 languages ==========
try {
  Object.defineProperty(navigator, 'languages', {
    get: _nativeGetter('languages', __LANGUAGES_JSON__),
    configurable: true,
  });
} catch (e) {}

// ========== 10. 伪造 chrome 对象 ==========
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

// ========== 11. UA-CH / navigator.userAgentData 伪造 ==========
try {
  const uaCh = __UA_CH_JSON__;
  if (uaCh && navigator.userAgentData) {
    const makeUad = function () {
      const brands = uaCh.brands || uaCh.fullVersionList || [];
      const base = {
        brands: brands,
        mobile: !!uaCh.mobile,
        platform: uaCh.platform || 'Windows',
        toJSON: _nativeFn('toJSON', function () { return { brands: brands, mobile: !!uaCh.mobile, platform: uaCh.platform || 'Windows' }; }),
      };
      base.getHighEntropyValues = _nativeFn('getHighEntropyValues', async function (hints) {
        const out = { brands: brands, mobile: !!uaCh.mobile, platform: uaCh.platform || 'Windows' };
        const want = Array.isArray(hints) ? hints : [];
        const map = {
          architecture: uaCh.architecture,
          bitness: uaCh.bitness,
          model: uaCh.model,
          platformVersion: uaCh.platformVersion,
          uaFullVersion: uaCh.uaFullVersion,
          fullVersionList: uaCh.fullVersionList,
          wow64: uaCh.wow64,
        };
        for (var i = 0; i < want.length; i++) {
          var k = want[i];
          if (k in map && map[k] !== undefined) out[k] = map[k];
        }
        return out;
      });
      return base;
    };
    Object.defineProperty(navigator, 'userAgentData', {
      get: _nativeGetter('userAgentData', makeUad()),
      configurable: true,
    });
  }
} catch (e) {}

// ========== 12. Battery API 伪造 ==========
try {
  if (navigator.getBattery) {
    navigator.getBattery = _nativeFn('getBattery', function () {
      return Promise.resolve({
        charging: __BATTERY_CHARGING__,
        chargingTime: 0,
        dischargingTime: Infinity,
        level: __BATTERY_LEVEL__,
        addEventListener: function () {},
        removeEventListener: function () {},
        dispatchEvent: function () { return true; },
      });
    });
  }
} catch (e) {}

// ========== 13. Connection 网络连接伪造 ==========
try {
  if (navigator.connection) {
    Object.defineProperty(navigator.connection, 'effectiveType', { get: _nativeGetter('effectiveType', '__CONNECTION_TYPE__'), configurable: true });
    Object.defineProperty(navigator.connection, 'downlink', { get: _nativeGetter('downlink', __CONNECTION_DOWNLINK__), configurable: true });
    Object.defineProperty(navigator.connection, 'rtt', { get: _nativeGetter('rtt', __CONNECTION_RTT__), configurable: true });
    Object.defineProperty(navigator.connection, 'saveData', { get: _nativeGetter('saveData', false), configurable: true });
  } else {
    // navigator.connection 不存在时兜底
    Object.defineProperty(navigator, 'connection', {
      get: _nativeGetter('connection', {
        effectiveType: '__CONNECTION_TYPE__',
        downlink: __CONNECTION_DOWNLINK__,
        rtt: __CONNECTION_RTT__,
        saveData: false,
        addEventListener: function () {},
        removeEventListener: function () {},
      }),
      configurable: true,
    });
  }
} catch (e) {}

// ========== 14. AudioContext 音频指纹噪声 ==========
try {
  const _audioSeed = __AUDIO_CONTEXT_SEED__;
  if (__PATCH_AUDIO_CONTEXT__ && typeof AudioContext !== 'undefined') {
    const _OrigAudioContext = AudioContext;
    window.AudioContext = _nativeFn('AudioContext', function () {
      const ctx = new _OrigAudioContext(...arguments);
      const _origCreateOsc = ctx.createOscillator.bind(ctx);
      ctx.createOscillator = _nativeFn('createOscillator', function () {
        const osc = _origCreateOsc();
        const _origStart = osc.start.bind(osc);
        osc.start = _nativeFn('start', function (when) {
          osc.frequency.value += (_audioSeed % 10) * 0.001;
          return _origStart(when);
        });
        return osc;
      });
      return ctx;
    });
  }
} catch (e) {}

// ========== 15. Canvas 指纹噪声（基于账号种子）==========
try {
  const _canvasSeed = __CANVAS_NOISE_SEED__;
  const _canvasStrength = __CANVAS_NOISE_STRENGTH__;

  function _applyCanvasNoise(imageData) {
    const data = imageData.data;
    const len = data.length;
    let lcg = (_canvasSeed * 1664525 + 1013904223) & 0xffffffff;
    let i = 0;
    while (i < len - 3) {
      const noise = (lcg ^ (_canvasSeed >> 3)) & 0x3;
      data[i] ^= noise * _canvasStrength;
      const step = 4 + (lcg & 0xf);
      lcg = (lcg * 1664525 + 1013904223) & 0xffffffff;
      i += step;
    }
  }

  const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = _nativeFn('toDataURL', function (type) {
    if (type === 'image/png' || type === 'image/webp' || !type) {
      const ctx2d = this.getContext('2d');
      if (ctx2d && this.width > 0 && this.height > 0) {
        try {
          const imgData = ctx2d.getImageData(0, 0, this.width, this.height);
          _applyCanvasNoise(imgData);
          ctx2d.putImageData(imgData, 0, 0);
        } catch (e) {}
      }
    }
    return _origToDataURL.apply(this, arguments);
  });

  const _origToBlob = HTMLCanvasElement.prototype.toBlob;
  HTMLCanvasElement.prototype.toBlob = _nativeFn('toBlob', function (callback, type, quality) {
    const mimeType = type || 'image/png';
    if (mimeType === 'image/png' || mimeType === 'image/webp') {
      const ctx2d = this.getContext('2d');
      if (ctx2d && this.width > 0 && this.height > 0) {
        try {
          const imgData = ctx2d.getImageData(0, 0, this.width, this.height);
          _applyCanvasNoise(imgData);
          ctx2d.putImageData(imgData, 0, 0);
        } catch (e) {}
      }
    }
    return _origToBlob.call(this, callback, type, quality);
  });

  // getImageData 路径：部分高级指纹库直接读取绕过 toDataURL
  const _origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
  CanvasRenderingContext2D.prototype.getImageData = _nativeFn('getImageData', function (sx, sy, sw, sh) {
    const imgData = _origGetImageData.call(this, sx, sy, sw, sh);
    if (sw >= 8 && sh >= 8) {
      try { _applyCanvasNoise(imgData); } catch (e) {}
    }
    return imgData;
  });
} catch (e) {}

// ========== 16. Font 字体指纹防护 ==========
try {
  const _commonFonts = new Set([
    'Arial', 'Verdana', 'Helvetica', 'Times New Roman', 'Courier New',
    'Georgia', 'Palatino', 'Garamond', 'Bookman', 'Comic Sans MS',
    'Trebuchet MS', 'Impact', 'Microsoft YaHei', 'SimSun', 'SimHei',
    'Microsoft JhengHei', 'FangSong', 'KaiTi',
  ]);

  if (document.fonts && document.fonts.check) {
    const _origFontsCheck = document.fonts.check.bind(document.fonts);
    document.fonts.check = _nativeFn('check', function (font, text) {
      const m = font.match(/"([^"]+)"|'([^']+)'|(\S+)/);
      const fontName = m ? (m[1] || m[2] || m[3]) : '';
      if (fontName && !_commonFonts.has(fontName)) return false;
      try { return _origFontsCheck(font, text); } catch (e) { return false; }
    });
  }

  if (document.fonts && document.fonts.load) {
    const _origFontsLoad = document.fonts.load.bind(document.fonts);
    document.fonts.load = _nativeFn('load', function (font, text) {
      const m = font.match(/"([^"]+)"|'([^']+)'|(\S+)/);
      const fontName = m ? (m[1] || m[2] || m[3]) : '';
      if (fontName && !_commonFonts.has(fontName)) return Promise.resolve([]);
      return _origFontsLoad(font, text);
    });
  }
} catch (e) {}

// ========== 17. Timezone 一致性保护 ==========
// 时区偏移量由 Python 注入（与 Playwright timezone_id 参数对应）
try {
  const _origGetTimezoneOffset = Date.prototype.getTimezoneOffset;
  Date.prototype.getTimezoneOffset = _nativeFn('getTimezoneOffset', function () {
    return __TIMEZONE_OFFSET__;
  });
} catch (e) {}

try {
  if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {
    const _OrigDTF = Intl.DateTimeFormat;
    Intl.DateTimeFormat = _nativeFn('DateTimeFormat', function (locales, options) {
      const newOptions = options || {};
      if (!newOptions.timeZone) {
        newOptions.timeZone = '__TIMEZONE_NAME__';
      }
      return new _OrigDTF(locales || 'zh-CN', newOptions);
    });
    Intl.DateTimeFormat.prototype = _OrigDTF.prototype;
    Intl.DateTimeFormat.supportedLocalesOf = _OrigDTF.supportedLocalesOf;
  }
} catch (e) {}

// ========== 18. WebRTC IP 泄露防护 ==========
try {
  if (typeof RTCPeerConnection !== 'undefined') {
    const _OrigRTC = RTCPeerConnection;
    window.RTCPeerConnection = _nativeFn('RTCPeerConnection', function () {
      const pc = new _OrigRTC(...arguments);
      const _origCreateOffer = pc.createOffer.bind(pc);
      pc.createOffer = _nativeFn('createOffer', function () {
        return _origCreateOffer(...arguments).then(function (offer) {
          if (offer.sdp) {
            offer.sdp = offer.sdp.replace(/c=IN IP4 \d+\.\d+\.\d+\.\d+/g, 'c=IN IP4 0.0.0.0');
            offer.sdp = offer.sdp.replace(/a=candidate:.+?(\r\n|\n|$)/g, '');
          }
          return offer;
        });
      });
      return pc;
    });
    if (typeof webkitRTCPeerConnection !== 'undefined') {
      window.webkitRTCPeerConnection = window.RTCPeerConnection;
    }
  }
} catch (e) {}

// ========== 19. Media Devices 伪造 ==========
try {
  if (__PATCH_MEDIA_DEVICES__ && navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
    const _fakeDevices = [
      { deviceId: '__MEDIA_AUDIO_IN_ID__', kind: 'audioinput', label: 'Default - Microphone (Realtek High Definition Audio)', groupId: '__MEDIA_AUDIO_GID__' },
      { deviceId: 'communications', kind: 'audioinput', label: 'Communications - Microphone (Realtek High Definition Audio)', groupId: '__MEDIA_AUDIO_GID__' },
      { deviceId: '__MEDIA_AUDIO_OUT_ID__', kind: 'audiooutput', label: 'Default - Speakers (Realtek High Definition Audio)', groupId: '__MEDIA_AUDIO_OUT_GID__' },
      { deviceId: '__MEDIA_VIDEO_ID__', kind: 'videoinput', label: 'HD Webcam (04f2:b5ce)', groupId: '__MEDIA_VIDEO_GID__' },
    ];
    navigator.mediaDevices.enumerateDevices = _nativeFn('enumerateDevices', function () {
      return Promise.resolve(_fakeDevices);
    });
  }
} catch (e) {}

// ========== 20. Permissions API ==========
try {
  if (__PATCH_PERMISSIONS__ && navigator.permissions && navigator.permissions.query) {
    const _origPermQuery = navigator.permissions.query.bind(navigator.permissions);
    const _permMap = {
      notifications: 'granted',
      geolocation: 'prompt',
      camera: 'prompt',
      microphone: 'prompt',
      'clipboard-read': 'denied',
      'clipboard-write': 'granted',
      'persistent-storage': 'granted',
      push: 'prompt',
      midi: 'prompt',
    };
    navigator.permissions.query = _nativeFn('query', function (params) {
      const name = params && (params.name || (params.descriptor && params.descriptor.name));
      if (name && _permMap[name]) return Promise.resolve({ state: _permMap[name] });
      return _origPermQuery.apply(this, arguments);
    });
  }
} catch (e) {}

// Notification.permission 伪装（与 permissionsMap 中 notifications 对齐）
try {
  if (typeof Notification !== 'undefined' && Notification.permission !== 'granted') {
    Object.defineProperty(Notification, 'permission', {
      get: _nativeGetter('permission', 'granted'),
      configurable: true,
    });
  }
} catch (e) {}

// ========== 21. 页面焦点与可见性伪造 ==========
try {
  Object.defineProperty(document, 'hidden', { get: _nativeGetter('hidden', false), configurable: true });
  Object.defineProperty(document, 'visibilityState', { get: _nativeGetter('visibilityState', 'visible'), configurable: true });
  document.hasFocus = _nativeFn('hasFocus', function () { return true; });
  document.addEventListener('visibilitychange', function (e) { e.stopImmediatePropagation(); }, true);
} catch (e) {}

// ========== 22. Headless 检测绕过 ==========
try {
  if (window.outerWidth === 0) {
    Object.defineProperty(window, 'outerWidth', { get: _nativeGetter('outerWidth', function () { return window.innerWidth; }), configurable: true });
  }
  if (window.outerHeight === 0) {
    Object.defineProperty(window, 'outerHeight', { get: _nativeGetter('outerHeight', function () { return window.innerHeight + 85; }), configurable: true });
  }
} catch (e) {}

// screen.orientation 兜底
try {
  if (!window.screen.orientation) {
    Object.defineProperty(window.screen, 'orientation', {
      get: _nativeGetter('orientation', { type: 'landscape-primary', angle: 0 }),
      configurable: true,
    });
  }
} catch (e) {}

// speechSynthesis 兜底（Headless 通常没有）
try {
  if (typeof window.speechSynthesis === 'undefined') {
    Object.defineProperty(window, 'speechSynthesis', {
      get: _nativeGetter('speechSynthesis', {
        getVoices: _nativeFn('getVoices', function () { return []; }),
        speak: function () {},
        cancel: function () {},
        pause: function () {},
        resume: function () {},
        pending: false, speaking: false, paused: false,
        addEventListener: function () {}, removeEventListener: function () {},
      }),
      configurable: true,
    });
  }
} catch (e) {}

// window.external 兜底
try {
  if (!window.external) {
    window.external = { AddSearchProvider: function () {}, IsSearchProviderInstalled: function () {} };
  }
} catch (e) {}

// ========== 23. performance.now() 时序微抖动 ==========
try {
  const _origPerfNow = performance.now.bind(performance);
  let _perfNowOffset = 0;
  performance.now = _nativeFn('now', function () {
    _perfNowOffset += (Math.random() - 0.5) * 0.16;
    if (_perfNowOffset > 2) _perfNowOffset = 2;
    if (_perfNowOffset < -2) _perfNowOffset = -2;
    return _origPerfNow() + _perfNowOffset;
  });
} catch (e) {}

// ========== 24. Error.stack 清理 ==========
// Error.stack 可能暴露 Playwright/CDP 内部调用堆栈路径
try {
  const _OrigError = Error;
  const _makeFilteredError = function (ErrorClass) {
    const _orig = ErrorClass.prototype;
    const _origCaptureStack = _orig.captureStackTrace;
    if (_origCaptureStack) {
      ErrorClass.prototype.captureStackTrace = _nativeFn('captureStackTrace', function (obj, constructorOpt) {
        _origCaptureStack.call(this, obj, constructorOpt);
        if (obj && obj.stack) {
          obj.stack = obj.stack.replace(/\s+at.*patchright.*/g, '').replace(/\s+at.*playwright.*/gi, '');
        }
      });
    }
    const _origPrepare = _orig.prepareStackTrace;
    if (_origPrepare) {
      ErrorClass.prepareStackTrace = _nativeFn('prepareStackTrace', function (err, stack) {
        const result = _origPrepare ? _origPrepare(err, stack) : '';
        if (typeof result === 'string') {
          return result.replace(/\s+at.*patchright.*/g, '').replace(/\s+at.*playwright.*/gi, '');
        }
        return result;
      });
    }
  };
  _makeFilteredError(Error);
} catch (e) {}
