// ========== 硬件参数伪造 ==========
Object.defineProperty(navigator, "hardwareConcurrency", {
  get: () => __HARDWARE_CONCURRENCY__,
});
Object.defineProperty(navigator, "deviceMemory", {
  get: () => __DEVICE_MEMORY__,
});

// ========== Screen 屏幕指纹伪造 ==========
Object.defineProperty(screen, "width", {
  get: () => __SCREEN_WIDTH__,
});
Object.defineProperty(screen, "height", {
  get: () => __SCREEN_HEIGHT__,
});
Object.defineProperty(screen, "availWidth", {
  get: () => __SCREEN_AVAIL_WIDTH__,
});
Object.defineProperty(screen, "availHeight", {
  get: () => __SCREEN_AVAIL_HEIGHT__,
});
Object.defineProperty(screen, "colorDepth", {
  get: () => __SCREEN_COLOR_DEPTH__,
});
Object.defineProperty(screen, "pixelDepth", {
  get: () => __SCREEN_PIXEL_DEPTH__,
});

// ========== WebGL 厂商与渲染器伪造 ==========
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function (parameter) {
  // 37445: UNMASKED_VENDOR_WEBGL
  // 37446: UNMASKED_RENDERER_WEBGL
  if (parameter === 37445) {
    return "__WEBGL_VENDOR__";
  }
  if (parameter === 37446) {
    return "__WEBGL_RENDERER__";
  }
  return getParameter.apply(this, arguments);
};

// 针对 WebGL2 也做同样的修补
if (typeof WebGL2RenderingContext !== "undefined") {
  const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
  WebGL2RenderingContext.prototype.getParameter = function (parameter) {
    if (parameter === 37445) {
      return "__WEBGL_VENDOR__";
    }
    if (parameter === 37446) {
      return "__WEBGL_RENDERER__";
    }
    return getParameter2.apply(this, arguments);
  };
}

// ========== Navigator 扩展属性伪造 ==========
Object.defineProperty(navigator, "platform", {
  get: () => "__PLATFORM__",
});
Object.defineProperty(navigator, "maxTouchPoints", {
  get: () => __MAX_TOUCH_POINTS__,
});
Object.defineProperty(navigator, "vendor", {
  get: () => "__VENDOR__",
});
Object.defineProperty(navigator, "vendorSub", {
  get: () => "__VENDOR_SUB__",
});
Object.defineProperty(navigator, "productSub", {
  get: () => "__PRODUCT_SUB__",
});

// ========== 隐藏 webdriver 属性 ==========
Object.defineProperty(navigator, "webdriver", {
  get: () => undefined,
});

// ========== 伪造插件列表 ==========
Object.defineProperty(navigator, "plugins", {
  get: () => [
    { name: "Chrome PDF Plugin", filename: "internal-pdf-viewer" },
    { name: "Chrome PDF Viewer", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai" },
    { name: "Native Client", filename: "internal-nacl-plugin" },
  ],
});

// ========== 伪造 languages ==========
Object.defineProperty(navigator, "languages", {
  get: () => __LANGUAGES_JSON__,
});

// ========== 伪造 chrome 对象 ==========
if (!window.chrome) {
  window.chrome = {
    runtime: {},
    loadTimes: function () {},
    csi: function () {},
    app: {},
  };
}

// ========== UA-CH / Client Hints 伪造 ==========
// 注意：这是“尽力而为”的伪装。若浏览器不支持 userAgentData，则安全降级。
try {
  const uaCh = __UA_CH_JSON__;
  if (uaCh && navigator.userAgentData) {
    const makeUad = () => {
      const brands = uaCh.brands || uaCh.fullVersionList || [];
      const base = {
        brands: brands,
        mobile: !!uaCh.mobile,
        platform: uaCh.platform || "Windows",
      };
      base.getHighEntropyValues = async (hints) => {
        const out = { ...base };
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
        for (const k of want) {
          if (k in map && map[k] !== undefined) out[k] = map[k];
        }
        return out;
      };
      return base;
    };
    Object.defineProperty(navigator, "userAgentData", {
      get: () => makeUad(),
      configurable: true,
    });
  }
} catch (e) {}

// ========== Battery API 伪造 ==========
if (navigator.getBattery) {
  navigator.getBattery = () =>
    Promise.resolve({
      charging: __BATTERY_CHARGING__,
      chargingTime: 0,
      dischargingTime: Infinity,
      level: __BATTERY_LEVEL__,
      addEventListener: function () {},
      removeEventListener: function () {},
      dispatchEvent: function () {},
    });
}

// ========== Connection 网络连接伪造 ==========
if (navigator.connection) {
  Object.defineProperty(navigator.connection, "effectiveType", {
    get: () => "__CONNECTION_TYPE__",
  });
  Object.defineProperty(navigator.connection, "downlink", {
    get: () => __CONNECTION_DOWNLINK__,
  });
  Object.defineProperty(navigator.connection, "rtt", {
    get: () => __CONNECTION_RTT__,
  });
}

// ========== AudioContext 音频指纹噪声 ==========
const audioContextSeed = __AUDIO_CONTEXT_SEED__;
if (__PATCH_AUDIO_CONTEXT__ && typeof AudioContext !== "undefined") {
  const OriginalAudioContext = AudioContext;
  window.AudioContext = function () {
    const context = new OriginalAudioContext(...arguments);
    const originalCreateOscillator = context.createOscillator.bind(context);
    context.createOscillator = function () {
      const oscillator = originalCreateOscillator();
      const originalStart = oscillator.start.bind(oscillator);
      oscillator.start = function (when) {
        // 添加基于种子的微小频率偏移
        oscillator.frequency.value += (audioContextSeed % 10) * 0.001;
        return originalStart(when);
      };
      return oscillator;
    };
    return context;
  };
}

// ========== Canvas 指纹噪声 (基于账号种子) ==========
const canvasNoiseSeed = __CANVAS_NOISE_SEED__;
const canvasNoiseStrength = __CANVAS_NOISE_STRENGTH__;
const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function (type) {
  if (type === "image/png" || type === "image/webp") {
    const canvas = this;
    const context = canvas.getContext("2d");
    if (context) {
      const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
      for (let i = 0; i < imageData.data.length; i += 4) {
        // 基于种子的确定性噪声
        const noise = (canvasNoiseSeed % 3) * (canvasNoiseStrength || 1);
        imageData.data[i] ^= noise;
      }
      context.putImageData(imageData, 0, 0);
    }
  }
  return originalToDataURL.apply(this, arguments);
};

// 补充 toBlob 路径：指纹库也会通过 toBlob 导出 Canvas 内容
const originalToBlob = HTMLCanvasElement.prototype.toBlob;
HTMLCanvasElement.prototype.toBlob = function (callback, type, quality) {
  const mimeType = type || "image/png";
  if (mimeType === "image/png" || mimeType === "image/webp") {
    const canvas = this;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      for (let i = 0; i < imageData.data.length; i += 4) {
        const noise = (canvasNoiseSeed % 3) * (canvasNoiseStrength || 1);
        imageData.data[i] ^= noise;
      }
      ctx.putImageData(imageData, 0, 0);
    }
  }
  return originalToBlob.call(this, callback, type, quality);
};

// ========== Font 字体指纹防护 ==========
// 字体指纹检测的主要手段：对比不同字体渲染同一字符串时 span 的 offsetWidth 差异
// 防护策略：
//   1. hook document.fonts.check() 使非白名单字体返回 false
//   2. 让 FontFace / FontFaceSet.load 对非白名单字体静默失败
const commonFonts = new Set([
  "Arial",
  "Verdana",
  "Helvetica",
  "Times New Roman",
  "Courier New",
  "Georgia",
  "Palatino",
  "Garamond",
  "Bookman",
  "Comic Sans MS",
  "Trebuchet MS",
  "Impact",
  "Microsoft YaHei",
  "SimSun",
  "SimHei",
]);

// hook document.fonts.check()：对白名单外的字体返回 false，模拟未安装
if (document.fonts && document.fonts.check) {
  const _origFontsCheck = document.fonts.check.bind(document.fonts);
  document.fonts.check = function (font, text) {
    const match = font.match(/"([^"]+)"|'([^']+)'|(\S+)/);
    const fontName = match ? (match[1] || match[2] || match[3]) : "";
    if (fontName && !commonFonts.has(fontName)) return false;
    try { return _origFontsCheck(font, text); } catch (e) { return false; }
  };
}

// hook FontFaceSet.load()：对白名单外的字体返回空列表，阻止探测
if (document.fonts && document.fonts.load) {
  const _origFontsLoad = document.fonts.load.bind(document.fonts);
  document.fonts.load = function (font, text) {
    const match = font.match(/"([^"]+)"|'([^']+)'|(\S+)/);
    const fontName = match ? (match[1] || match[2] || match[3]) : "";
    if (fontName && !commonFonts.has(fontName)) return Promise.resolve([]);
    return _origFontsLoad(font, text);
  };
}

// ========== Timezone 一致性保护 ==========
// 软件仅在中国使用，统一东八区 (UTC+8)，偏移量 -480
const originalGetTimezoneOffset = Date.prototype.getTimezoneOffset;
Date.prototype.getTimezoneOffset = function () {
  return -480; // UTC+8，与 Playwright timezone_id: Asia/Shanghai 一致
};

// ========== WebRTC IP 泄露完全防护 ==========
// 方案1: 完全禁用 RTCPeerConnection
if (typeof RTCPeerConnection !== "undefined") {
  const OriginalRTCPeerConnection = RTCPeerConnection;
  window.RTCPeerConnection = function () {
    const pc = new OriginalRTCPeerConnection(...arguments);

    // 拦截 createOffer,过滤真实IP
    const originalCreateOffer = pc.createOffer.bind(pc);
    pc.createOffer = function () {
      return originalCreateOffer(...arguments).then((offer) => {
        // 替换SDP中的真实IP为0.0.0.0
        if (offer.sdp) {
          offer.sdp = offer.sdp.replace(
            /c=IN IP4 \d+\.\d+\.\d+\.\d+/g,
            "c=IN IP4 0.0.0.0",
          );
          offer.sdp = offer.sdp.replace(/a=candidate:.+?(\r\n|\n|$)/g, "");
        }
        return offer;
      });
    };

    return pc;
  };

  // 同步处理 webkit 前缀
  if (typeof webkitRTCPeerConnection !== "undefined") {
    window.webkitRTCPeerConnection = window.RTCPeerConnection;
  }
}

// ========== Media Devices 伪造 ==========
if (__PATCH_MEDIA_DEVICES__ && navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
  const fakeDevices = [
    {
      deviceId: "default",
      kind: "audioinput",
      label: "Default - Microphone (Realtek High Definition Audio)",
      groupId: "group-audio-input-1",
    },
    {
      deviceId: "communications",
      kind: "audioinput",
      label: "Communications - Microphone (Realtek High Definition Audio)",
      groupId: "group-audio-input-1",
    },
    {
      deviceId: "default",
      kind: "audiooutput",
      label: "Default - Speakers (Realtek High Definition Audio)",
      groupId: "group-audio-output-1",
    },
    {
      deviceId: "webcam-1",
      kind: "videoinput",
      label: "HD Webcam (04f2:b5ce)",
      groupId: "group-video-input-1",
    },
  ];

  navigator.mediaDevices.enumerateDevices = () => Promise.resolve(fakeDevices);
}

// ========== Permissions API 完善 ==========
if (__PATCH_PERMISSIONS__ && navigator.permissions && navigator.permissions.query) {
  const originalPermissionsQuery = navigator.permissions.query;
  const permissionsMap = {
    notifications: "granted",
    geolocation: "prompt",
    camera: "prompt",
    microphone: "prompt",
    "clipboard-read": "denied",
    "clipboard-write": "granted",
    "persistent-storage": "granted",
    push: "prompt",
    midi: "prompt",
  };

  navigator.permissions.query = function (params) {
    const permName =
      params.name || (params.descriptor && params.descriptor.name);
    if (permName && permissionsMap[permName]) {
      return Promise.resolve({ state: permissionsMap[permName] });
    }
    return originalPermissionsQuery.apply(this, arguments);
  };
}

// ========== Intl 国际化一致性 ==========
// 软件仅在中国使用，统一 zh-CN + Asia/Shanghai，与 Playwright locale/timezone_id 参数一致
if (typeof Intl !== "undefined" && Intl.DateTimeFormat) {
  const OriginalDateTimeFormat = Intl.DateTimeFormat;
  Intl.DateTimeFormat = function (locales, options) {
    const newLocales = locales || "zh-CN";
    const newOptions = options || {};
    if (!newOptions.timeZone) {
      newOptions.timeZone = "Asia/Shanghai";
    }
    return new OriginalDateTimeFormat(newLocales, newOptions);
  };

  // 保留原型链
  Intl.DateTimeFormat.prototype = OriginalDateTimeFormat.prototype;
  Intl.DateTimeFormat.supportedLocalesOf =
    OriginalDateTimeFormat.supportedLocalesOf;
}

// ========== CDP/Playwright/Puppeteer 检测绕过 ==========
// 删除自动化工具留下的痕迹
delete window.__playwright;
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

// ========== Headless 检测绕过 ==========
// 伪造 window.outerWidth/outerHeight (headless模式下这些值为0)
if (window.outerWidth === 0) {
  Object.defineProperty(window, "outerWidth", {
    get: () => window.innerWidth,
  });
}
if (window.outerHeight === 0) {
  Object.defineProperty(window, "outerHeight", {
    get: () => window.innerHeight + 85, // 加上浏览器UI高度
  });
}

// 伪造 chrome.runtime (headless模式下可能缺失)
if (window.chrome && !window.chrome.runtime) {
  window.chrome.runtime = {
    connect: function () {},
    sendMessage: function () {},
    onMessage: {
      addListener: function () {},
      removeListener: function () {},
    },
  };
}

// ========== 其他高级伪造 ==========
// 伪造 window.external (IE遗留,但某些检测会查看)
if (!window.external) {
  window.external = {
    AddSearchProvider: function () {},
    IsSearchProviderInstalled: function () {},
  };
}

// 伪造 navigator.mimeTypes
Object.defineProperty(navigator, "mimeTypes", {
  get: () => [
    {
      type: "application/pdf",
      suffixes: "pdf",
      description: "Portable Document Format",
    },
    {
      type: "application/x-google-chrome-pdf",
      suffixes: "pdf",
      description: "Portable Document Format",
    },
  ],
});

// 确保 navigator.doNotTrack 存在
if (typeof navigator.doNotTrack === "undefined") {
  Object.defineProperty(navigator, "doNotTrack", {
    get: () => null,
  });
}
