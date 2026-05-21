# -*- coding: utf-8 -*-
"""
步骤8B：定时发表设置
文件路径：src/plugins/pro/wechat_video/steps/step_08B_schedule.py

操作序列（来自《视频号定时发布 - 时间选择器 DOM 分析报告》第七节验证结果）：
  立即发布（schedule_time 为空）→ 跳过，直接完成。
  定时发布：
    0. 滚动定时区域到视口
    1. 真实点击「定时」单选按钮
    2. 真实点击「发表时间」输入框 → 打开日历弹窗
    3. 翻月箭头导航到目标年月
    4. 真实点击目标日期
    5. 真实点击时间行「时间」区域 → 打开时分列表
    6. 真实点击目标小时 li
    7. 真实点击目标分钟 li
    8. 关闭弹窗：点击「发表时间」标签区域（视频/图文页通用，标签不被弹窗遮挡）
    9. 校验：主输入框值与目标一致 + 弹窗已关闭

所有元素在 wujie-app Shadow DOM 内，通过 page.evaluate() 穿透访问。
参考文档：docs/03插件系统/OpenClaw 报告分析报告/视频号定时发布 - 时间选择器 DOM 分析报告.md
"""
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..wujie_shadow import WUJIE_SHADOW_ROOT_JS as _SHADOW_JS

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

# ─── Shadow DOM + picker 根节点前缀 ───────────────────────────────────────────

_SHADOW_PREFIX = f"const shadow = {_SHADOW_JS}; if (!shadow) return null;"

# 在「发表时间」form-item 内定位 weui-desktop-picker__date-time，避免页面其他 picker 干扰
_PICKER_ROOT_JS = """
(function () {
    const labels = shadow.querySelectorAll('.form-item .label');
    for (const label of labels) {
        if ((label.textContent || '').trim().includes('发表时间')) {
            const fi = label.closest('.form-item');
            if (fi) {
                const p = fi.querySelector('.weui-desktop-picker__date-time');
                if (p) return p;
            }
        }
    }
    return shadow.querySelector('.weui-desktop-picker__date-time');
})()
""".strip()

_PICKER_PREFIX = (
    _SHADOW_PREFIX
    + f" const pickerRoot = {_PICKER_ROOT_JS}; if (!pickerRoot) return null;"
)


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def _parse_schedule_time(s: str) -> Optional[Tuple[int, int, int, int, int]]:
    """解析 "YYYY-MM-DD HH:MM" 或 "YYYY/MM/DD HH:MM"，返回 (年, 月, 日, 时, 分)。"""
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            return dt.year, dt.month, dt.day, dt.hour, dt.minute
        except ValueError:
            pass
    return None


def _parse_input_value(text: str) -> Optional[Tuple[int, int, int, int, int]]:
    """从主输入框展示文本解析 (年, 月, 日, 时, 分)，失败返回 None。"""
    if not text:
        return None
    m = re.search(
        r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2})",
        text.strip(),
    )
    if m:
        return tuple(int(m.group(i)) for i in range(1, 6))  # type: ignore[return-value]
    return None


async def _read_schedule_picker_state(page: Page) -> Dict[str, Any]:
    """读取「发表时间」picker 当前状态，供 SubmitStep（发表前）校验使用。

    返回字典：
      ok        - bool，能否正常读取
      inputValue - 主输入框当前展示字符串
      selectedHour / selectedMinute - 时分列表当前高亮项（弹窗关闭后为空字符串）
      reason    - 失败时的原因描述
    """
    js = """() => {
        """ + _SHADOW_PREFIX + """
        const pickerRoot = """ + _PICKER_ROOT_JS + """;
        if (!pickerRoot) return { ok: false, reason: 'no_picker', inputValue: '', selectedHour: '', selectedMinute: '' };
        const inp = pickerRoot.querySelector('dt .weui-desktop-form__input, dt input');
        const inputValue = inp ? (inp.value || '').trim() : '';
        const hourLi = pickerRoot.querySelector('.weui-desktop-picker__time__hour li.weui-desktop-picker__selected');
        const minuteLi = pickerRoot.querySelector('.weui-desktop-picker__time__minute li.weui-desktop-picker__selected');
        return {
            ok: true,
            inputValue: inputValue,
            selectedHour: hourLi ? hourLi.textContent.trim() : '',
            selectedMinute: minuteLi ? minuteLi.textContent.trim() : '',
        };
    }"""
    try:
        result = await page.evaluate(js)
        if isinstance(result, dict):
            return result
        return {"ok": False, "reason": "unexpected_result", "inputValue": "", "selectedHour": "", "selectedMinute": ""}
    except Exception as e:
        return {"ok": False, "reason": str(e), "inputValue": "", "selectedHour": "", "selectedMinute": ""}


def _schedule_matches_target(
    state: Dict[str, Any],
    target: Tuple[int, int, int, int, int],
) -> Tuple[bool, str]:
    """校验 picker 状态是否与目标定时时间一致，供 SubmitStep 使用。"""
    if not state.get("ok"):
        return False, str(state.get("reason") or "picker 不可用")
    inp = (state.get("inputValue") or "").strip()
    parsed = _parse_input_value(inp)
    if not parsed:
        return False, f"无法从输入框解析时间：{inp!r}"
    if parsed != target:
        y, mo, d, h, mi = target
        return False, f"输入框显示 {inp!r}，期望 {y}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}"
    return True, ""


async def _eval_xy(page: Page, tail_js: str) -> Optional[Tuple[float, float]]:
    """在 shadow + pickerRoot 已解析的环境中执行 tail_js，须 return {x,y} 或 null。"""
    js = "() => { " + _PICKER_PREFIX + " " + tail_js + " }"
    try:
        r = await page.evaluate(js)
        if isinstance(r, dict) and "x" in r and "y" in r:
            return float(r["x"]), float(r["y"])
    except Exception as e:
        logger.debug("[视频号] _eval_xy 异常: %s", e)
    return None


async def _eval_xy_shadow(page: Page, tail_js: str) -> Optional[Tuple[float, float]]:
    """在 shadow 已解析但无需 pickerRoot 的环境中执行 tail_js。"""
    js = "() => { " + _SHADOW_PREFIX + " " + tail_js + " }"
    try:
        r = await page.evaluate(js)
        if isinstance(r, dict) and "x" in r and "y" in r:
            return float(r["x"]), float(r["y"])
    except Exception as e:
        logger.debug("[视频号] _eval_xy_shadow 异常: %s", e)
    return None


async def _real_click(page: Page, xy: Optional[Tuple[float, float]]) -> bool:
    """在视口坐标处执行真实鼠标左键单击（isTrusted=true）。"""
    if not xy:
        return False
    try:
        await page.mouse.click(xy[0], xy[1])
        return True
    except Exception as e:
        logger.debug("[视频号] _real_click 失败: %s", e)
        return False


async def _read_main_input(page: Page) -> str:
    """读取「发表时间」主输入框的展示值。"""
    js = """() => {
        """ + _SHADOW_PREFIX + """
        const pickerRoot = """ + _PICKER_ROOT_JS + """;
        if (!pickerRoot) return '';
        const inp = pickerRoot.querySelector('dt .weui-desktop-form__input, dt input');
        return inp ? (inp.value || '').trim() : '';
    }"""
    try:
        return str(await page.evaluate(js) or "").strip()
    except Exception:
        return ""


async def _picker_is_open(page: Page) -> bool:
    """判断日期/时间选择弹窗是否打开。

    依据报告：微信 picker 弹窗使用 definition 元素（HTML 的 <dd>），
    同时检查 display/visibility/opacity 以及 BoundingClientRect 是否有尺寸。
    """
    js = """() => {
        """ + _SHADOW_PREFIX + """
        const pickerRoot = """ + _PICKER_ROOT_JS + """;
        if (!pickerRoot) return false;

        // 检测 definition（<dd>）元素是否可见
        const dds = pickerRoot.querySelectorAll('dd, definition');
        for (const el of dds) {
            let visible = true;
            let n = el;
            while (n && n !== pickerRoot) {
                const s = window.getComputedStyle(n);
                if (s.display === 'none' || s.visibility === 'hidden') { visible = false; break; }
                if (parseFloat(s.opacity || '1') < 0.05) { visible = false; break; }
                n = n.parentElement;
            }
            if (!visible) continue;
            const r = el.getBoundingClientRect();
            if (r.width > 4 && r.height > 4) return true;
        }

        const chainVisible = (el) => {
            let n = el;
            while (n && n !== pickerRoot) {
                const s = window.getComputedStyle(n);
                if (s.display === 'none' || s.visibility === 'hidden') return false;
                if (parseFloat(s.opacity || '1') < 0.05) return false;
                n = n.parentElement;
            }
            return true;
        };

        // 兜底：日历表格或时分列表可见即判定为打开
        for (const sel of [
            '.weui-desktop-picker__table',
            '.weui-desktop-picker__time__hour',
            '.weui-desktop-picker__time__minute',
        ]) {
            const el = pickerRoot.querySelector(sel);
            if (!el) continue;
            if (!chainVisible(el)) continue;
            const s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') continue;
            const r = el.getBoundingClientRect();
            if (r.width > 10 && r.height > 10) return true;
        }
        return false;
    }"""
    try:
        return bool(await page.evaluate(js))
    except Exception:
        return False


async def _close_picker(page: Page, wait_ms: int) -> bool:
    """关闭时间选择弹窗：点击「发表时间」标签区域。

    弹窗在日期输入框正下方展开，左侧「发表时间」四字不会被遮挡；
    视频发布页与图文发布页均有该表单项，此法两者通用。
    """
    xy_label = await _eval_xy_shadow(page, """
        const labels = shadow.querySelectorAll('.form-item .label');
        for (const label of labels) {
            const t = (label.textContent || '').trim();
            if (t === '发表时间' || t.includes('发表时间')) {
                try { label.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                const r = label.getBoundingClientRect();
                if (r.width > 1 && r.height > 1) {
                    return { x: r.left + r.width * 0.5, y: r.top + r.height * 0.5 };
                }
            }
        }
        return null;
    """)
    if not await _real_click(page, xy_label):
        logger.warning("[视频号] 无法点击「发表时间」标签区域")
        return False
    await page.wait_for_timeout(wait_ms)
    if not await _picker_is_open(page):
        logger.info("[视频号] 点击「发表时间」标签已关闭弹窗")
        return True
    logger.warning("[视频号] 点击「发表时间」标签后弹窗仍未关闭")
    return False


# ─── 主步骤类 ─────────────────────────────────────────────────────────────────

class ScheduleSettingStep(BasePublishStep):
    """步骤 8：定时发表设置。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

        def w(base_ms: int) -> int:
            return max(100, int(base_ms * speed_rate))

        schedule_time = (
            metadata.get("scheduled_publish_time")
            or metadata.get("schedule_time")
            or ""
        ).strip()

        logger.info("[视频号] 步骤 8：定时发表设置（时间='%s'）", schedule_time)

        # ── 步骤 0：滚动定时区域到视口 ────────────────────────────────────────
        try:
            await page.evaluate(f"""() => {{
                const shadow = {_SHADOW_JS};
                if (!shadow) return;
                // 优先找定时单选控件，滚动到中间
                const spans = shadow.querySelectorAll('span.weui-desktop-form__check-content');
                for (const s of spans) {{
                    if ((s.textContent || '').trim().includes('定时')) {{
                        const el = s.closest('label') || s;
                        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        return;
                    }}
                }}
                // 兜底：找含「定时」字样的 label
                const labels = shadow.querySelectorAll('.form-item .label');
                for (const l of labels) {{
                    if ((l.textContent || '').includes('定时')) {{
                        l.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        return;
                    }}
                }}
            }}""")
        except Exception as e:
            logger.debug("[视频号] 滚动到定时区域异常（忽略）: %s", e)

        await page.wait_for_timeout(w(1200))

        # ── 立即发布：不操作 ──────────────────────────────────────────────────
        if not schedule_time:
            logger.info("[视频号] 未配置定时，使用默认「不定时」，跳过步骤 8")
            return None

        # ── 解析目标时间 ──────────────────────────────────────────────────────
        parsed = _parse_schedule_time(schedule_time)
        if not parsed:
            return PublishResult(
                success=False,
                error_message=f"定时时间格式不正确：{schedule_time!r}（支持 YYYY-MM-DD HH:MM）",
                failed_step="ScheduleSettingStep",
            )
        t_year, t_month, t_day, t_hour, t_minute = parsed
        hour_str = f"{t_hour:02d}"
        minute_str = f"{t_minute:02d}"
        target = (t_year, t_month, t_day, t_hour, t_minute)

        # ── 步骤 1：点击「定时」单选按钮 ─────────────────────────────────────
        xy_radio = await _eval_xy_shadow(page, """
            const spans = shadow.querySelectorAll('span.weui-desktop-form__check-content');
            for (const s of spans) {
                const t = (s.textContent || '').trim();
                if (t === '定时' || t === '定时发表') {
                    const el = s.closest('label') || s;
                    try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                    const r = el.getBoundingClientRect();
                    if (r.width > 1 && r.height > 1) {
                        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
                    }
                }
            }
            // 兜底：直接用 CSS 定位单选
            const radio = shadow.querySelector(".weui-desktop-form__radio[value='1']");
            if (radio) {
                const el = radio.closest('label') || radio;
                try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                const r = el.getBoundingClientRect();
                if (r.width > 1 && r.height > 1) {
                    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
                }
            }
            return null;
        """)
        if not await _real_click(page, xy_radio):
            return PublishResult(
                success=False,
                error_message="无法点击「定时」单选按钮，请确保页面未被遮挡后重试",
                failed_step="ScheduleSettingStep",
            )
        logger.info("[视频号] 已点击「定时」单选按钮")

        # ── 步骤 2：等待 picker 组件渲染，再点击「发表时间」输入框 ─────────────
        # 点击「定时」后前端需要时间渲染 .weui-desktop-picker__date-time，
        # 连续发布时页面响应可能变慢，此处轮询等待而非固定延时。
        _PICKER_INPUT_JS = """
            // 优先点击 dt（term 元素），避免直接点 input 导致 toggle 问题
            const dt = pickerRoot.querySelector('dt');
            if (dt) {
                try { dt.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                const r = dt.getBoundingClientRect();
                if (r.width > 1 && r.height > 1) {
                    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
                }
            }
            // 兜底：直接点输入框
            const inp = pickerRoot.querySelector('.weui-desktop-form__input, input');
            if (!inp) return null;
            try { inp.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
            const r = inp.getBoundingClientRect();
            return (r.width > 1 && r.height > 1) ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : null;
        """
        xy_input = None
        max_picker_wait = 10
        for _poll in range(max_picker_wait):
            await page.wait_for_timeout(w(600))
            xy_input = await _eval_xy(page, _PICKER_INPUT_JS)
            if xy_input:
                break
            if _poll == 0:
                logger.debug("[视频号] picker 尚未渲染，继续轮询...")

        if not await _real_click(page, xy_input):
            return PublishResult(
                success=False,
                error_message="无法打开日历选择器，请确认定时控件已显示",
                failed_step="ScheduleSettingStep",
            )
        logger.info("[视频号] 已点击「发表时间」输入框，等待日历弹窗展开")
        await page.wait_for_timeout(w(2000))

        # ── 步骤 3：翻月导航到目标年月 ───────────────────────────────────────
        target_ym = t_year * 12 + t_month

        for _ in range(24):
            cur = await page.evaluate(f"""() => {{
                const shadow = {_SHADOW_JS};
                if (!shadow) return null;
                const pickerRoot = {_PICKER_ROOT_JS};
                if (!pickerRoot) return null;
                const hd = pickerRoot.querySelector('.weui-desktop-picker__panel__hd');
                if (!hd) return null;
                const labels = hd.querySelectorAll('.weui-desktop-picker__panel__label');
                if (labels.length < 2) return null;
                return {{
                    year: parseInt(labels[0].textContent.trim()),
                    month: parseInt(labels[1].textContent.trim()),
                }};
            }}""")
            if not cur or not isinstance(cur, dict):
                logger.warning("[视频号] 无法读取日历当前年月，停止翻月")
                break

            cur_ym = cur["year"] * 12 + cur["month"]
            if cur_ym == target_ym:
                logger.info("[视频号] 已到达目标年月：%d年%d月", t_year, t_month)
                break

            if cur_ym < target_ym:
                # 点下一月（右箭头）
                xy_nav = await _eval_xy(page, """
                    const hd = pickerRoot.querySelector('.weui-desktop-picker__panel__hd');
                    if (!hd) return null;
                    const btn = hd.querySelector('.weui-desktop-btn__icon__right');
                    if (!btn) return null;
                    try { btn.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                    const r = btn.getBoundingClientRect();
                    return (r.width > 1 && r.height > 1) ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : null;
                """)
                if not await _real_click(page, xy_nav):
                    logger.warning("[视频号] 无法点击下一月箭头，停止翻月")
                    break
            else:
                # 点上一月（左箭头）
                xy_nav = await _eval_xy(page, """
                    const hd = pickerRoot.querySelector('.weui-desktop-picker__panel__hd');
                    if (!hd) return null;
                    const btn = hd.querySelector('.weui-desktop-btn__icon__left');
                    if (!btn || btn.style.display === 'none') return null;
                    try { btn.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                    const r = btn.getBoundingClientRect();
                    return (r.width > 1 && r.height > 1) ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : null;
                """)
                if not xy_nav:
                    return PublishResult(
                        success=False,
                        error_message=f"定时时间 {schedule_time} 的月份已过期，无法选择",
                        failed_step="ScheduleSettingStep",
                    )
                if not await _real_click(page, xy_nav):
                    logger.warning("[视频号] 无法点击上一月箭头，停止翻月")
                    break

            await page.wait_for_timeout(w(600))

        # ── 步骤 4：点击目标日期 ──────────────────────────────────────────────
        xy_day = await _eval_xy(page, f"""
            const target = '{t_day}';
            const cells = pickerRoot.querySelectorAll('.weui-desktop-picker__table-row td a');
            let el = null;
            for (const a of cells) {{
                const day = a.textContent.trim();
                const disabled = a.classList.contains('weui-desktop-picker__disabled');
                const faded = a.classList.contains('weui-desktop-picker__faded');
                if (day === target && !disabled && !faded) {{ el = a; break; }}
            }}
            if (!el) return null;
            try {{ el.scrollIntoView({{ block: 'center', inline: 'nearest' }}); }} catch (e) {{}}
            const r = el.getBoundingClientRect();
            return (r.width > 1 && r.height > 1) ? {{ x: r.left + r.width / 2, y: r.top + r.height / 2 }} : null;
        """)
        if not await _real_click(page, xy_day):
            return PublishResult(
                success=False,
                error_message=f"无法选择日期 {t_day} 号（不在当前月或已禁用）",
                failed_step="ScheduleSettingStep",
            )
        logger.info("[视频号] 已选择日期：%d 号", t_day)
        await page.wait_for_timeout(w(1200))

        # ── 步骤 5：点击时间区域打开时分列表 ─────────────────────────────────
        # 报告验证：点击 term（dt）元素 e375 打开时间列表
        xy_time_dt = await _eval_xy(page, """
            const timeArea = pickerRoot.querySelector('.weui-desktop-picker__time');
            if (!timeArea) return null;
            const dt = timeArea.querySelector('dt');
            if (dt) {
                try { dt.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                const r = dt.getBoundingClientRect();
                if (r.width > 1 && r.height > 1) {
                    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
                }
            }
            // 兜底：点时间输入框
            const inp = timeArea.querySelector('input, .weui-desktop-form__input');
            if (!inp) return null;
            try { inp.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
            const r = inp.getBoundingClientRect();
            return (r.width > 1 && r.height > 1) ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : null;
        """)
        if not await _real_click(page, xy_time_dt):
            return PublishResult(
                success=False,
                error_message="无法打开时间列表，请确认日期面板仍展开",
                failed_step="ScheduleSettingStep",
            )
        logger.info("[视频号] 已点击时间区域，等待时分列表展开")
        await page.wait_for_timeout(w(2000))

        # ── 步骤 6：点击目标小时 ──────────────────────────────────────────────
        xy_hour = await _eval_xy(page, f"""
            const h = '{hour_str}';
            const items = pickerRoot.querySelectorAll('.weui-desktop-picker__time__hour li');
            let el = null;
            for (const li of items) {{
                if (li.textContent.trim() === h && !li.classList.contains('weui-desktop-picker__disabled')) {{
                    el = li; break;
                }}
            }}
            if (!el) return null;
            try {{ el.scrollIntoView({{ block: 'nearest', inline: 'nearest' }}); }} catch (e) {{}}
            const r = el.getBoundingClientRect();
            return (r.width > 1 && r.height > 1) ? {{ x: r.left + r.width / 2, y: r.top + r.height / 2 }} : null;
        """)
        if not await _real_click(page, xy_hour):
            return PublishResult(
                success=False,
                error_message=f"无法选择小时 {hour_str}（列表未展开或已禁用）",
                failed_step="ScheduleSettingStep",
            )
        logger.info("[视频号] 已选择小时：%s", hour_str)
        await page.wait_for_timeout(w(700))

        # ── 步骤 7：点击目标分钟 ──────────────────────────────────────────────
        xy_minute = await _eval_xy(page, f"""
            const m = '{minute_str}';
            const items = pickerRoot.querySelectorAll('.weui-desktop-picker__time__minute li');
            let el = null;
            for (const li of items) {{
                if (li.textContent.trim() === m && !li.classList.contains('weui-desktop-picker__disabled')) {{
                    el = li; break;
                }}
            }}
            if (!el) return null;
            try {{ el.scrollIntoView({{ block: 'nearest', inline: 'nearest' }}); }} catch (e) {{}}
            const r = el.getBoundingClientRect();
            return (r.width > 1 && r.height > 1) ? {{ x: r.left + r.width / 2, y: r.top + r.height / 2 }} : null;
        """)
        if not await _real_click(page, xy_minute):
            return PublishResult(
                success=False,
                error_message=f"无法选择分钟 {minute_str}（列表未展开或已禁用）",
                failed_step="ScheduleSettingStep",
            )
        logger.info("[视频号] 已选择分钟：%s", minute_str)
        await page.wait_for_timeout(w(800))

        USER_LOG.info(
            "%s 时分已选择（%s:%s），准备关闭弹窗并校验",
            self._step_prefix(metadata, "定时发表"),
            hour_str,
            minute_str,
        )

        # ── 步骤 8：关闭弹窗 ──────────────────────────────────────────────────
        closed = await _close_picker(page, w(500))
        if not closed:
            displayed_after_close = await _read_main_input(page)
            parsed_after_close = _parse_input_value(displayed_after_close)
            picker_still_open = await _picker_is_open(page)
            if parsed_after_close == target:
                logger.warning(
                    "[视频号] 未确认 picker 已关闭，但输入框时间已正确写入，继续后续步骤: displayed=%s open=%s",
                    displayed_after_close,
                    picker_still_open,
                )
            elif picker_still_open:
                return PublishResult(
                    success=False,
                    error_message="定时时间弹窗多次操作后仍未关闭，请勿遮挡浏览器窗口后重试",
                    failed_step="ScheduleSettingStep",
                )

        await page.wait_for_timeout(w(400))

        # ── 步骤 9：校验主输入框值与目标一致 ─────────────────────────────────
        displayed = await _read_main_input(page)
        parsed_displayed = _parse_input_value(displayed)

        if parsed_displayed != target:
            logger.error(
                "[视频号] 定时校验失败：输入框='%s' 解析=%s 目标=%s",
                displayed, parsed_displayed, target,
            )
            return PublishResult(
                success=False,
                error_message=(
                    f"定时时间校验失败：页面显示 {displayed!r}，"
                    f"期望 {t_year}-{t_month:02d}-{t_day:02d} {hour_str}:{minute_str}"
                ),
                failed_step="ScheduleSettingStep",
            )

        logger.info(
            "[视频号] 步骤 8 完成：定时发表已设置并校验通过 → %d-%02d-%02d %s:%s",
            t_year, t_month, t_day, hour_str, minute_str,
        )
        USER_LOG.info(
            "%s ✓ 定时时间设置成功：%d-%02d-%02d %s:%s",
            self._step_prefix(metadata, "定时发表"),
            t_year,
            t_month,
            t_day,
            hour_str,
            minute_str,
        )
        return None
