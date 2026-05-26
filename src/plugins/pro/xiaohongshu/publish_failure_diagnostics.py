# -*- coding: utf-8 -*-
"""小红书发布失败时的诊断包扩展（closed Shadow / xhs-publish-btn）。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from playwright.async_api import Page

from ._xhs_submit_probe import (
    evaluate_sr_red_button_state,
    snapshot_xhs_publish_btn,
    summarize_snapshot_for_log,
)

logger = logging.getLogger(__name__)

_HOST_PROBE_JS = """(el) => {
    if (!el) return { hostFound: false };
    let srAccess = 'none';
    let sr = null;
    if (el._sr && typeof el._sr.querySelector === 'function') {
        sr = el._sr;
        srAccess = '_sr';
    } else if (el.shadowRoot && typeof el.shadowRoot.querySelector === 'function') {
        sr = el.shadowRoot;
        srAccess = 'shadowRoot';
    }
    const buttons = sr
        ? [...sr.querySelectorAll('button.ce-btn')].map((btn, i) => {
            const r = btn.getBoundingClientRect();
            return {
                index: i,
                text: (btn.innerText || btn.textContent || '').trim(),
                className: btn.className || '',
                width: Math.round(r.width),
                height: Math.round(r.height),
            };
        })
        : [];
    return {
        hostFound: true,
        isPublish: el.getAttribute('is-publish') || '',
        submitText: el.getAttribute('submit-text') || '',
        submitDisabled: el.getAttribute('submit-disabled') || '',
        saveText: el.getAttribute('save-text') || '',
        srAccessMethod: srAccess,
        hasSr: Boolean(el._sr),
        hasOpenShadowRoot: Boolean(el.shadowRoot),
        shadowButtonCount: buttons.length,
        shadowButtons: buttons,
    };
}"""


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _attached_snapshot(metadata: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(metadata, Mapping):
        return None
    ctx = metadata.get("_diagnostic_context")
    if not isinstance(ctx, Mapping):
        return None
    raw = ctx.get("xhs_publish_snapshot_raw")
    if isinstance(raw, dict):
        return dict(raw)
    summary = ctx.get("xhs_publish_snapshot")
    if isinstance(summary, dict):
        return {"summary_from_step": summary}
    return None


async def _resolve_publish_host(page: Page):
    for sel in (
        ".publish-page-content xhs-publish-btn[is-publish='true']",
        "xhs-publish-btn[is-publish='true']",
        "xhs-publish-btn",
    ):
        loc = page.locator(sel).first
        if await loc.count() > 0:
            return loc
    return page.locator("xhs-publish-btn").first


async def probe_xhs_publish_host(page: Page) -> Dict[str, Any]:
    """在宿主 locator 上 evaluate，探测 _sr 与 Shadow 内按钮。"""
    host = await _resolve_publish_host(page)
    if await host.count() == 0:
        return {"hostFound": False, "hostCount": 0}
    try:
        raw = await host.evaluate(_HOST_PROBE_JS)
        if isinstance(raw, dict):
            return raw
    except Exception as e:
        return {"hostFound": False, "error": str(e)}
    return {"hostFound": False}


async def _merge_snapshot(
    page: Page,
    metadata: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    attached = _attached_snapshot(metadata)
    live = await snapshot_xhs_publish_btn(page)
    if attached and live.get("hostCount", 0) == 0:
        attached["source"] = "step_attach"
        attached["captured_at"] = datetime.now().isoformat(timespec="seconds")
        return attached
    if attached and live.get("hostCount", 0) > 0:
        live["source"] = "capture_with_step_attach_available"
        live["step_attach_summary"] = summarize_snapshot_for_log(attached)
    else:
        live["source"] = "capture"
    live["captured_at"] = datetime.now().isoformat(timespec="seconds")
    return live


def build_xhs_failure_analysis(
    *,
    step_name: str,
    reason: str,
    summary: Dict[str, Any],
    probe: Dict[str, Any],
    page_url: str = "",
) -> Dict[str, Any]:
    """生成结构化中文分析（供 platform_analysis.json 与 UI hints）。"""
    hints: list[str] = []
    likely: list[str] = []
    checks: list[str] = []

    host_count = int(summary.get("host_count") or summary.get("hostCount") or 0)
    submit_disabled = bool(summary.get("submit_disabled"))
    picker_open = bool(summary.get("schedule_picker_open"))
    focus_sched = bool(summary.get("focus_in_schedule"))
    has_sr = bool(summary.get("has_sr") or probe.get("hasSr"))
    sr_method = probe.get("srAccessMethod") or "none"
    sr_ready = bool(probe.get("ready")) if "ready" in probe else summary.get("red_button_ready")

    hints.append(
        "小红书发布钮在 closed Shadow 内：通用 dom_snapshot 可能看不到内部按钮，"
        "请以本目录 xhs_publish_snapshot.json / xhs_publish_probe.json 为准。"
    )
    if sr_method == "_sr":
        hints.append("已通过组件内部 _sr 访问 Shadow（实采验证方案）。")
    elif sr_method == "shadowRoot":
        hints.append("通过 open shadowRoot 访问 Shadow（与 closed 模式不同，请留意平台是否改版）。")
    else:
        hints.append("未能访问 Shadow（_sr 与 shadowRoot 均不可用），发布钮点击可能失败。")
        likely.append("Web Component 内部结构变更，_sr 引用失效。")

    if host_count == 0:
        hints.append("页面上未检测到 xhs-publish-btn：可能未进入完整发布编辑页，或视频/必填项未完成。")
        likely.append("仍在首页/上传中，或发布表单未渲染底部发布栏。")
        checks.append("确认视频已上传、标题等必填项已填写，并滚动到页面底部。")
    else:
        submit_text = summary.get("submit_text") or probe.get("submitText") or ""
        if submit_text:
            hints.append(f"宿主 submit-text 当前为「{submit_text}」。")

    if submit_disabled:
        hints.append("发布钮宿主 submit-disabled=true，平台认为尚不可提交。")
        likely.append("表单校验未通过、定时时间浮层未关闭，或焦点仍在定时输入框。")
        checks.append("关闭定时日期浮层；点击设置区空白失焦；确认定时时间合法且在未来。")
    if picker_open:
        hints.append("定时日期浮层仍处于打开状态，可能挡住底部发布钮。")
        checks.append("点击页面右侧预览区空白或按 Esc 关闭定时浮层。")
    if focus_sched:
        hints.append("焦点仍在「定时发布」输入区域，可能导致 submit-disabled 不解除。")
        checks.append("先完成定时设置并点击页面其他区域失焦。")

    red_reason = probe.get("reason") or ""
    if red_reason == "text_mismatch":
        hints.append(
            f"Shadow 红钮文案与 submit-text 不一致（probe: {probe.get('expected')} vs {probe.get('text')}）。"
        )
    elif red_reason == "red_btn_missing" and host_count > 0:
        likely.append("Shadow 内未找到 button.ce-btn.bg-red，页面结构可能改版。")

    if step_name == "SubmitStep":
        checks.append("查看 screenshot.png 与 page.html 对照是否仍在 /publish/publish 编辑页。")
    if "timeout" in (reason or "").lower() or "超时" in (reason or ""):
        likely.append("等待发布钮可点击超时（常见于 submit-disabled 长期为 true）。")

    if sr_method != "none" and host_count > 0:
        hints.append(
            "selector_probes 中 pierce（>>）计数为 0 属正常，不代表页面缺少发布按钮。"
        )

    return {
        "platform": "xiaohongshu",
        "step_name": step_name,
        "reason": reason,
        "page_url": page_url,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "hints": hints[:8],
        "likely_causes": likely[:6],
        "recommended_checks": checks[:6],
        "summary": summary,
        "probe": {
            "srAccessMethod": sr_method,
            "hostFound": probe.get("hostFound", host_count > 0),
            "submitDisabled": probe.get("submitDisabled") or submit_disabled,
            "submitText": probe.get("submitText") or summary.get("submit_text"),
            "shadowButtons": probe.get("shadowButtons") or summary.get("shadow_buttons"),
            "srRedReady": sr_ready,
            "srBlockReason": red_reason or None,
        },
    }


def format_analysis_txt(analysis: Dict[str, Any]) -> str:
    lines = [
        "小红书发布失败 · 页面结构分析说明",
        "=" * 40,
        f"失败步骤：{analysis.get('step_name', '')}",
        f"原因摘要：{analysis.get('reason', '')}",
        "",
        "【提示】",
    ]
    for h in analysis.get("hints") or []:
        lines.append(f"  · {h}")
    if analysis.get("likely_causes"):
        lines.extend(["", "【可能原因】"])
        for c in analysis.get("likely_causes") or []:
            lines.append(f"  · {c}")
    if analysis.get("recommended_checks"):
        lines.extend(["", "【建议检查】"])
        for c in analysis.get("recommended_checks") or []:
            lines.append(f"  · {c}")
    lines.extend([
        "",
        "详细数据见同目录：xhs_publish_snapshot.json、xhs_publish_probe.json",
    ])
    return "\n".join(lines) + "\n"


async def capture_xiaohongshu_extras(
    page: Page,
    bundle_dir: Path,
    metadata: Optional[Mapping[str, Any]],
    *,
    step_name: str = "",
    reason: str = "",
    page_url: str = "",
) -> Dict[str, Any]:
    """
    写入小红书专用诊断文件，返回合并进 metadata.json 的摘要字段。
    """
    bundle_dir.mkdir(parents=True, exist_ok=True)

    snapshot = await _merge_snapshot(page, metadata)
    _write_json(bundle_dir / "xhs_publish_snapshot.json", snapshot)
    summary = summarize_snapshot_for_log(snapshot)

    host_probe = await probe_xhs_publish_host(page)
    primary = (summary.get("submit_text") or "发布").strip() or "发布"
    host = await _resolve_publish_host(page)
    sr_state: Dict[str, Any] = {}
    if await host.count() > 0:
        sr_state = await evaluate_sr_red_button_state(host, primary)
    probe_out = {**host_probe, **sr_state}
    _write_json(bundle_dir / "xhs_publish_probe.json", probe_out)

    analysis = build_xhs_failure_analysis(
        step_name=step_name,
        reason=reason,
        summary=summary,
        probe=probe_out,
        page_url=page_url,
    )
    _write_json(bundle_dir / "platform_analysis.json", analysis)
    try:
        (bundle_dir / "分析说明.txt").write_text(
            format_analysis_txt(analysis),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug("写入分析说明.txt 失败: %s", e)

    meta_extra = {
        "xhs_publish_snapshot": summary,
        "xhs_submit_disabled": summary.get("submit_disabled"),
        "xhs_sr_accessible": host_probe.get("srAccessMethod") not in (None, "", "none"),
        "xhs_sr_access_method": host_probe.get("srAccessMethod"),
        "xhs_submit_text": summary.get("submit_text"),
        "xhs_host_count": summary.get("host_count", 0),
        "xhs_shadow_buttons": summary.get("shadow_buttons"),
        "xhs_analysis_hints": analysis.get("hints", [])[:5],
    }
    logger.info(
        "小红书诊断扩展已写入: %s (hosts=%s, sr=%s)",
        bundle_dir,
        summary.get("host_count"),
        host_probe.get("srAccessMethod"),
    )
    return meta_extra


def load_analysis_hints_from_bundle(diagnostic_path: str, *, max_hints: int = 5) -> list[str]:
    """从诊断包目录读取 platform_analysis.json 的 hints（供 UI 弹窗）。"""
    folder = Path((diagnostic_path or "").strip())
    if not folder.is_dir():
        return []
    analysis_file = folder / "platform_analysis.json"
    if not analysis_file.is_file():
        return []
    try:
        data = json.loads(analysis_file.read_text(encoding="utf-8"))
        hints = data.get("hints")
        if isinstance(hints, list):
            return [str(h) for h in hints[:max_hints] if h]
    except Exception:
        pass
    return []
