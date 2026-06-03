const statusEl = document.getElementById("status");

function value(id) {
  return document.getElementById(id).value.trim();
}

function testRunId() {
  return value("testRunId") || new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
}

document.getElementById("collect").addEventListener("click", async () => {
  statusEl.textContent = "Collecting...";
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    if (!tab || !tab.id) {
      throw new Error("No active tab.");
    }
    const options = {
      platform: value("platform"),
      mode: value("mode"),
      stage: value("stage"),
      test_run_id: testRunId()
    };
    const response = await chrome.runtime.sendMessage({
      type: "COLLECT_DIAGNOSTIC",
      tabId: tab.id,
      url: tab.url || "",
      options
    });
    if (!response || !response.ok) {
      throw new Error(response && response.error ? response.error : "Collection failed.");
    }
    statusEl.textContent = `Downloaded ${response.filename}`;
  } catch (err) {
    statusEl.textContent = String(err && err.message ? err.message : err);
  }
});

