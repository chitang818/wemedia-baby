const RISK_PROMPT_KEYWORDS = [
  "操作频繁", "风控", "异常验证", "安全验证", "验证失败", "环境异常", "风险",
  "稍后重试", "脚本", "自动化", "自动化软件", "AI", "人工智能", "验证码"
];

function sanitizeCookie(cookie) {
  return {
    name: cookie.name || "",
    domain: cookie.domain || "",
    path: cookie.path || "",
    expires: cookie.expirationDate || null,
    httpOnly: !!cookie.httpOnly,
    secure: !!cookie.secure,
    sameSite: cookie.sameSite || ""
  };
}

function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  return chrome.downloads.download({url, filename, saveAs: true});
}

async function collectPageEnvironment(tabId, options) {
  const [{result}] = await chrome.scripting.executeScript({
    target: {tabId},
    func: async (opts, keywords) => {
      const safe = async (fn, fallback = null) => {
        try { return await fn(); } catch (_) { return fallback; }
      };
      const visible = (el) => {
        try {
          const rect = el.getBoundingClientRect();
          const style = window.getComputedStyle(el);
          return rect.width > 0 && rect.height > 0 &&
            style.display !== "none" && style.visibility !== "hidden" &&
            parseFloat(style.opacity || "1") > 0.05;
        } catch (_) {
          return false;
        }
      };
      const readWebgl = () => {
        const canvas = document.createElement("canvas");
        const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
        if (!gl) return {supported: false};
        const dbg = gl.getExtension("WEBGL_debug_renderer_info");
        return {
          supported: true,
          vendor: gl.getParameter(gl.VENDOR),
          renderer: gl.getParameter(gl.RENDERER),
          unmaskedVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : "",
          unmaskedRenderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : ""
        };
      };
      const readPermission = async (name) => {
        if (!navigator.permissions || !navigator.permissions.query) return "unsupported";
        try {
          const status = await navigator.permissions.query({name});
          return status && status.state ? status.state : "unknown";
        } catch (_) {
          return "error";
        }
      };
      const bodyText = (document.body && document.body.innerText || "").replace(/\s+/g, " ").trim();
      const riskPrompts = [];
      for (const keyword of keywords) {
        const idx = bodyText.indexOf(keyword);
        if (idx >= 0) {
          riskPrompts.push({
            keyword,
            snippet: bodyText.slice(Math.max(0, idx - 40), Math.min(bodyText.length, idx + 100))
          });
        }
      }
      const visibleDialogs = Array.from(document.querySelectorAll("[role='dialog'], [role='alert'], .dialog, .modal, [class*='toast'], [class*='message']"))
        .filter(visible)
        .slice(0, 20)
        .map((el) => (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 240))
        .filter(Boolean);
      const uaData = await safe(async () => {
        if (!navigator.userAgentData) return null;
        const high = navigator.userAgentData.getHighEntropyValues
          ? await navigator.userAgentData.getHighEntropyValues([
            "architecture", "bitness", "model", "platform", "platformVersion",
            "uaFullVersion", "fullVersionList"
          ])
          : {};
        return {
          brands: navigator.userAgentData.brands || [],
          mobile: navigator.userAgentData.mobile,
          platform: navigator.userAgentData.platform,
          highEntropy: high
        };
      }, null);
      return {
        collector: "chrome_extension",
        extension_present: true,
        controlled_by_playwright: "unknown",
        platform: opts.platform,
        mode: opts.mode,
        stage: opts.stage,
        test_run_id: opts.test_run_id,
        captured_at: new Date().toISOString(),
        page_environment: {
          url: location.href,
          title: document.title,
          readyState: document.readyState,
          navigator: {
            userAgent: navigator.userAgent,
            webdriver: navigator.webdriver,
            platform: navigator.platform,
            vendor: navigator.vendor,
            productSub: navigator.productSub,
            language: navigator.language,
            languages: navigator.languages ? Array.from(navigator.languages) : [],
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory,
            maxTouchPoints: navigator.maxTouchPoints,
            cookieEnabled: navigator.cookieEnabled,
            doNotTrack: navigator.doNotTrack,
            plugins: Array.from(navigator.plugins || []).slice(0, 20).map((p) => ({
              name: p.name,
              filename: p.filename,
              description: p.description
            })),
            mimeTypesLength: navigator.mimeTypes ? navigator.mimeTypes.length : null,
            userAgentData: uaData
          },
          screen: {
            width: screen.width,
            height: screen.height,
            availWidth: screen.availWidth,
            availHeight: screen.availHeight,
            colorDepth: screen.colorDepth,
            pixelDepth: screen.pixelDepth
          },
          viewport: {
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            outerWidth: window.outerWidth,
            outerHeight: window.outerHeight,
            devicePixelRatio: window.devicePixelRatio
          },
          locale: {
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            dateTimeLocale: Intl.DateTimeFormat().resolvedOptions().locale
          },
          permissions: {
            notifications: await readPermission("notifications"),
            geolocation: await readPermission("geolocation"),
            camera: await readPermission("camera"),
            microphone: await readPermission("microphone")
          },
          webgl: readWebgl(),
          storage: {
            localStorageKeys: await safe(() => Object.keys(localStorage || {}).slice(0, 80), []),
            sessionStorageKeys: await safe(() => Object.keys(sessionStorage || {}).slice(0, 80), [])
          },
          visibleDialogs
        },
        risk_prompt_snippets: riskPrompts
      };
    },
    args: [options, RISK_PROMPT_KEYWORDS]
  });
  return result;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "COLLECT_DIAGNOSTIC") {
    return false;
  }
  (async () => {
    try {
      const tabId = message.tabId;
      const options = message.options || {};
      const pageSnapshot = await collectPageEnvironment(tabId, options);
      const cookies = await chrome.cookies.getAll({url: message.url});
      pageSnapshot.cookies = cookies.map(sanitizeCookie);
      pageSnapshot.cookie_count = pageSnapshot.cookies.length;
      pageSnapshot.notes = [
        "Cookie values are intentionally omitted.",
        "This extension is read-only and does not modify page state.",
        "extension_present=true must be considered part of the observed environment."
      ];
      const filename = `wemediababy-browser-diagnostic-${options.platform || "unknown"}-${options.mode || "unknown"}-${options.stage || "unknown"}-${options.test_run_id || Date.now()}.json`;
      await downloadJson(filename, pageSnapshot);
      sendResponse({ok: true, filename});
    } catch (err) {
      sendResponse({ok: false, error: String(err && err.message ? err.message : err)});
    }
  })();
  return true;
});

