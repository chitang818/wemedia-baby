# -*- coding: utf-8 -*-
"""
步骤5：作品描述（标题与正文）
文件路径: src/plugins/pro/xiaohongshu/steps/step_05_description.py

流程：
  1. 标题填写：温和滚入视口（顶部留白）→ 定位 TITLE_INPUT → 逐字输入（限 20 字）
  2. 正文/描述填写：
     - 预处理：parse_topic_list 解析话题并打日志
     - 滚动描述编辑器至视口偏上位置（约 25% 处，上方仍可见上传区/标题等）
     - 阶段 A：仅输入剥除 #话题 后的纯正文（keyboard 逐字）
     - 阶段 B：输入词名 → 检测话题下拉出现 → 点建议（若有）→ Space；DOM+文本后验
  3. metadata.tags 中未出现在文案的话题会追加到输入列表末尾

字段依赖：
  - metadata['title']: 标题（小红书限 20 字）
  - metadata['description']: 描述/正文
  - metadata['tags']: 话题标签列表
  - metadata['speed_rate']: 打字速度倍率
"""
import logging
import re
from typing import Any, Dict, List, Tuple

from playwright.async_api import Locator, Page

from src.domain.publish.work_description import parse_topic_list
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

_TOPIC_PREVIEW_MAX = 12

# 小红书描述区话题常为 <a>/<span> 蓝链，innerText 不一定含可解析的 #，需 DOM 采集
_EXTRACT_TOPICS_JS = """(root) => {
    if (!root) return [];
    const seen = new Set();
    const out = [];
    const push = (raw) => {
        let t = (raw || '').trim();
        while (t.startsWith('#')) t = t.slice(1).trim();
        t = t.replace(/\\[话题\\]#?$/g, '').replace(/\\[话题\\]/g, '').trim();
        while (t.endsWith('#')) t = t.slice(0, -1).trim();
        if (t && t.length <= 50 && !seen.has(t)) {
            seen.add(t);
            out.push(t);
        }
    };
    const isTopicEl = (el) => {
        const cls = (el.className && String(el.className)) || '';
        const tag = (el.nodeName || '').toLowerCase();
        if (tag === 'a') return true;
        return /topic|hashtag|mention|tag/i.test(cls);
    };
    root.querySelectorAll('a, span').forEach((el) => {
        if (!root.contains(el)) return;
        const t = (el.textContent || '').trim();
        if (!t || t.length > 50) return;
        if (t.startsWith('#') || isTopicEl(el)) push(t);
    });
    const text = root.innerText || root.textContent || '';
    const re = /#([^\\s#\\u3000-\\u3011，。！？；：、,.!?;:()（）【】{}《》""''\\\\/|<>@%^&*=+]+)/g;
    let m;
    while ((m = re.exec(text)) !== null) push('#' + m[1]);
    return out;
}"""


def _topic_type_delay(speed_rate: float) -> int:
    """话题词名较短，逐字间隔低于正文。"""
    return max(5, int(16 * max(0.5, speed_rate)))


def _topic_pause_ms(base_ms: int, speed_rate: float) -> int:
    """话题阶段专用停顿（约为原固定等待的一半，仍随 speed_rate 缩放）。"""
    return max(10, int(base_ms * 0.5 * max(0.5, speed_rate)))


async def _type_chinese_with_ime(
    page: Page, text: str, speed_rate: float, default_delay: int
) -> None:
    """模拟中文 IME 输入过程（拼音 → 选字），有效绕过直接赋值特征。"""
    import random
    
    pypinyin_mod = None
    try:
        import pypinyin
        pypinyin_mod = pypinyin
    except ImportError:
        pass

    for char in text:
        if pypinyin_mod and '\u4e00' <= char <= '\u9fff':
            try:
                pinyin = pypinyin_mod.pinyin(char, style=pypinyin_mod.NORMAL)[0][0]
                await page.evaluate(
                    "() => document.activeElement && document.activeElement.dispatchEvent(new CompositionEvent('compositionstart', {bubbles:true}))"
                )
                await page.keyboard.type(pinyin, delay=random.randint(40, 90))
                await page.evaluate(
                    f"() => document.activeElement && document.activeElement.dispatchEvent(new CompositionEvent('compositionend', {{bubbles:true, data:'{char}'}}))"
                )
                await page.keyboard.insert_text(char)
            except Exception:
                await page.keyboard.type(char, delay=default_delay)
        else:
            await page.keyboard.type(char, delay=default_delay)
            
        await page.wait_for_timeout(random.randint(int(20 * speed_rate), int(80 * speed_rate)))


def _normalize_meta_tag_entries(tags: List[str]) -> List[str]:
    """与 parse_topic_list 输出可比：去空白、去前导井号（含全角）。"""
    out: List[str] = []
    for t in tags:
        if t is None:
            continue
        s = str(t).strip().replace("\uff03", "").lstrip("#").strip()
        if s:
            out.append(s)
    return out


def _format_topics_for_log(topics: List[str]) -> str:
    if not topics:
        return "（无）"
    head = topics[:_TOPIC_PREVIEW_MAX]
    s = "、".join(head)
    if len(topics) > _TOPIC_PREVIEW_MAX:
        s += f" …共{len(topics)}个"
    return s


def _split_body_and_topics(description: str, tags_meta: List[str]) -> Tuple[str, List[str]]:
    """从描述剥除 #话题 得纯正文；话题列表=文案顺序 + 未出现的 tags。"""
    desc = (description or "").strip()
    from_desc = parse_topic_list(desc)
    seen = set(from_desc)
    merged = list(from_desc)
    for t in _normalize_meta_tag_entries(tags_meta):
        if t and t not in seen:
            seen.add(t)
            merged.append(t)
    body = re.sub(r"#\s*[^\s#]+", " ", desc)
    body = re.sub(r"\s+", " ", body).strip()
    return body, merged


def _log_description_topic_preprocess(description: str, tags_meta: List[str]) -> List[str]:
    """发布侧描述步骤专用：按全站规则解析文案内话题并打日志。"""
    raw = description or ""
    parsed = parse_topic_list(raw)
    meta_norm = _normalize_meta_tag_entries(tags_meta)

    logger.info(
        "【描述预处理】从本任务作品描述解析到 %d 个话题（规则同 topics.parse_topic_list）：%s",
        len(parsed),
        parsed,
    )
    logger.info(
        "【描述预处理】metadata.tags 共 %d 项（去井号后）=%s",
        len(meta_norm),
        meta_norm,
    )

    if len(parsed) != len(meta_norm):
        logger.warning(
            "【描述预处理】文案解析话题数(%d) 与 metadata.tags 项数(%d) 不一致，请核对批量/文案库是否把描述与 tags 同步下发",
            len(parsed),
            len(meta_norm),
        )
    elif parsed and meta_norm and set(parsed) != set(meta_norm):
        logger.warning(
            "【描述预处理】话题数量一致但词条集合不同：文案=%s tags=%s",
            parsed,
            meta_norm,
        )

    USER_LOG.info(
        "[步骤5 作品描述] ▶ 预处理：从文案解析到 %d 个话题「%s」",
        len(parsed),
        _format_topics_for_log(parsed),
    )
    if meta_norm:
        USER_LOG.info(
            "[步骤5 作品描述] ▶ 预处理：任务携带 tags %d 项「%s」",
            len(meta_norm),
            _format_topics_for_log(meta_norm),
        )
    else:
        USER_LOG.info("[步骤5 作品描述] ▶ 预处理：任务未单独携带 tags（仅以文案为准）")
    if len(parsed) != len(meta_norm):
        USER_LOG.warning(
            "[步骤5 作品描述] ⚠ 文案解析话题数(%d) 与 tags 项数(%d) 不一致，请查任务配置/文案库",
            len(parsed),
            len(meta_norm),
        )

    return parsed


def _topic_label_for_type(tag: str) -> str:
    """输入用话题词名：去掉首尾空白与全部前导 #（含误传的 ##）。"""
    s = (tag or "").strip().replace("\uff03", "")
    while s.startswith("#"):
        s = s[1:].lstrip()
    return s


def _normalize_editor_topic_name(raw: str) -> str:
    """编辑器 DOM 采集名规范化（如 蔬菜种植[话题]# → 蔬菜种植）。"""
    s = _topic_label_for_type(raw)
    s = re.sub(r"\[话题\]", "", s)
    while s.endswith("#"):
        s = s[:-1].strip()
    return s.strip()


def _distinct_normalized_topics(collected: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in collected:
        n = _normalize_editor_topic_name(item)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _topic_label_in_collected(label: str, collected: List[str]) -> bool:
    want = _normalize_editor_topic_name(label)
    if not want:
        return False
    return want in {_normalize_editor_topic_name(c) for c in collected}


def should_use_topic_entry_btn(topic_index: int, in_topic_compose: bool) -> bool:
    """仅首个话题或不在话题编辑态时才点「# 话题」按钮。"""
    return topic_index == 0 or not in_topic_compose


def _truncate_topics_to_limit(topics: List[str], max_topics: int) -> Tuple[List[str], bool]:
    if max_topics <= 0 or len(topics) <= max_topics:
        return topics, False
    return topics[:max_topics], True


def _topic_count_in_text(text: str) -> int:
    """从纯文本解析 #话题 个数（与任务侧 parse_topic_list 规则一致）。"""
    return len(parse_topic_list(text or ""))


def _merge_editor_topic_names(dom_topics: List[str], inner_text: str) -> List[str]:
    """合并 DOM 采集与 innerText 解析（供单测与后验）。"""
    raw_all = list(dom_topics or []) + parse_topic_list(inner_text or "")
    return _distinct_normalized_topics([str(x) for x in raw_all])


async def _get_editor_inner_text(page: Page, edit_box: Locator) -> str:
    try:
        handle = await edit_box.element_handle()
        if not handle:
            return ""
        return (await page.evaluate("el => el.innerText || ''", handle)) or ""
    except Exception:
        return ""


async def _extract_topics_from_editor(page: Page, edit_box: Locator) -> List[str]:
    """从描述编辑器采集已收成话题（DOM 蓝链 + innerText 兜底）。"""
    try:
        handle = await edit_box.element_handle()
        if not handle:
            return []
        dom_topics = await page.evaluate(_EXTRACT_TOPICS_JS, handle)
        if not isinstance(dom_topics, list):
            dom_topics = []
        inner = await _get_editor_inner_text(page, edit_box)
        return _merge_editor_topic_names(dom_topics, inner)
    except Exception as e:
        logger.debug("采集编辑器话题失败: %s", e)
        inner = await _get_editor_inner_text(page, edit_box)
        return parse_topic_list(inner)


async def _count_topics_in_editor(page: Page, edit_box: Locator) -> int:
    """统计描述区已收成话题数。"""
    return len(await _extract_topics_from_editor(page, edit_box))


async def _caret_in_topic_compose(page: Page, edit_box: Locator) -> bool:
    """光标是否处于话题编辑态（前字符为 # 或在话题 composing 节点内）。"""
    try:
        handle = await edit_box.element_handle()
        if not handle:
            return False
        return bool(
            await page.evaluate(
                """(root) => {
                    const sel = window.getSelection();
                    if (!sel || sel.rangeCount === 0) return false;
                    const range = sel.getRangeAt(0);
                    if (!root.contains(range.startContainer)) return false;
                    let node = range.startContainer;
                    let offset = range.startOffset;
                    if (node.nodeType === Node.TEXT_NODE) {
                        const text = node.textContent || '';
                        if (offset > 0 && text.charAt(offset - 1) === '#') return true;
                        if (offset < text.length && text.charAt(offset) === '#') return true;
                        node = node.parentElement;
                    }
                    while (node && node !== root) {
                        const cls = (node.className && String(node.className)) || '';
                        const tag = (node.nodeName || '').toLowerCase();
                        if (tag === 'a' || /topic|hashtag|tag/i.test(cls)) return true;
                        node = node.parentElement;
                    }
                    return false;
                }""",
                handle,
            )
        )
    except Exception as e:
        logger.debug("检测话题编辑态失败: %s", e)
        return False


async def _fix_double_hash_before_caret(page: Page, edit_box: Locator) -> None:
    """兜底：光标前若为 ## 则 Backspace 删掉多余 #。"""
    try:
        handle = await edit_box.element_handle()
        if not handle:
            return
        need_backspace = await page.evaluate(
            """(root) => {
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return false;
                const range = sel.getRangeAt(0);
                if (!root.contains(range.startContainer)) return false;
                if (range.startContainer.nodeType !== Node.TEXT_NODE) return false;
                const text = range.startContainer.textContent || '';
                const off = range.startOffset;
                return off >= 2 && text.slice(off - 2, off) === '##';
            }""",
            handle,
        )
        if need_backspace:
            await page.keyboard.press("Backspace")
            logger.info("已修正光标前双井号 ##")
    except Exception as e:
        logger.debug("修正双井号失败: %s", e)


async def _click_topic_entry_btn_scoped(
    page: Page, edit_box: Locator, *, speed_rate: float = 1.0
) -> bool:
    """在描述编辑器附近点击「# 话题」，避免误点侧栏。"""
    scope = edit_box.locator("xpath=ancestor::div[position()<=10]")
    for selector in Selectors.PUBLISH.get("TOPIC_ENTRY_BTN") or []:
        for base in (scope, page):
            try:
                btn = base.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(_topic_pause_ms(90, speed_rate))
                    return True
            except Exception:
                continue
    return False


async def _is_topic_dropdown_visible(page: Page) -> bool:
    """话题建议下拉是否已出现在页面上。"""
    for selector in Selectors.PUBLISH.get("TOPIC_DROPDOWN") or []:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            continue
    for selector in Selectors.PUBLISH.get("TOPIC_SUGGESTION") or []:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            continue
    return False


async def _wait_for_topic_dropdown(
    page: Page, *, speed_rate: float = 1.0, max_ms: int | None = None
) -> bool:
    """短轮询等待话题下拉（上限约 200ms，避免无下拉时干等）。"""
    interval = max(18, _topic_pause_ms(22, speed_rate))
    budget = max_ms if max_ms is not None else max(160, _topic_pause_ms(220, speed_rate))
    spent = 0
    while spent < budget:
        if await _is_topic_dropdown_visible(page):
            return True
        await page.wait_for_timeout(interval)
        spent += interval
    return False


async def _try_pick_topic_suggestion_hit(
    page: Page, label: str, *, click_timeout_ms: int = 500
) -> bool:
    """仅尝试点击与 label 完全匹配的建议项（不做方向键，节省时间）。"""
    for selector in Selectors.PUBLISH.get("TOPIC_SUGGESTION") or []:
        try:
            exact = page.locator(selector).filter(has_text=label).first
            if await exact.count() > 0 and await exact.is_visible():
                await exact.click(timeout=click_timeout_ms)
                return True
        except Exception:
            continue
    return False


async def _confirm_topic_when_dropdown_ready(
    page: Page, label: str, *, speed_rate: float = 1.0
) -> str:
    """短等下拉 → 可点则点建议 → 空格收成（主路径不阻塞在 no_dropdown 长等待）。"""
    if not label:
        return "miss"

    # 给弹层极短启动时间，随后高频检测
    await page.wait_for_timeout(max(35, _topic_pause_ms(45, speed_rate)))
    dropdown_seen = await _wait_for_topic_dropdown(page, speed_rate=speed_rate)

    if dropdown_seen and await _try_pick_topic_suggestion_hit(page, label):
        await _press_space_after_topic(page, speed_rate=speed_rate, settle_ms=50)
        return "hit"

    await _press_space_after_topic(page, speed_rate=speed_rate, settle_ms=70)
    return "space" if dropdown_seen else "fast_space"


async def _press_space_after_topic(
    page: Page, *, speed_rate: float = 1.0, settle_ms: int = 70
) -> None:
    """空格收成话题芯片。"""
    await page.keyboard.press("Space")
    await page.wait_for_timeout(_topic_pause_ms(settle_ms, speed_rate))


async def _log_editor_topics_postcheck(
    page: Page, edit_box: Locator, expected_labels: List[str]
) -> None:
    """按 DOM+文本采集话题后验，并检测重复输入。"""
    if not expected_labels:
        return
    try:
        parsed = _distinct_normalized_topics(
            await _extract_topics_from_editor(page, edit_box)
        )
        actual = await _get_editor_inner_text(page, edit_box)
        expected_count = len(expected_labels)
        if len(parsed) < expected_count:
            missing = [
                t
                for t in expected_labels
                if not _topic_label_in_collected(t, parsed)
            ]
            logger.warning(
                "话题后验：采集到 %d 个话题 %s，期望 %d，缺失: %s",
                len(parsed),
                parsed,
                expected_count,
                missing,
            )
            USER_LOG.warning(
                "[步骤5 作品描述] ⚠ 话题后验 %d/%d，未命中：%s",
                len(parsed),
                expected_count,
                "、".join(missing[:5]),
            )
        else:
            logger.info(
                "话题后验：采集话题数=%d，期望=%d，列表=%s",
                len(parsed),
                expected_count,
                parsed,
            )
        dup = [t for t in expected_labels if parsed.count(_normalize_editor_topic_name(t)) > 1]
        if dup:
            logger.warning("话题后验：描述中出现重复话题: %s", dup)
            USER_LOG.warning(
                "[步骤5 作品描述] ⚠ 描述中存在重复话题：%s",
                "、".join(dup[:5]),
            )
        if "##" in actual:
            logger.warning("话题后验：innerText 仍含双井号 ##")
            USER_LOG.warning("[步骤5 作品描述] ⚠ 描述中仍存在 ##，请检查输入时序")
    except Exception as e:
        logger.debug("话题后验异常: %s", e)


# 输入区滚入视口时，元素顶边距视口顶部的比例（0.25 ≈ 上方留 1/4 屏给上传/标题区）
_SCROLL_VIEWPORT_TOP_RATIO = 0.25


async def _scroll_locator_into_comfortable_view(
    page: Page,
    locator: Locator,
    metadata: Dict[str, Any],
    config: Dict[str, Any],
    *,
    wait_ms: int = 400,
    viewport_top_ratio: float = _SCROLL_VIEWPORT_TOP_RATIO,
) -> None:
    """将输入区滚入可视范围：顶边约在视口 25% 处，避免 block:start 把描述框顶死到最上方。"""
    ratio = max(0.12, min(0.45, float(viewport_top_ratio)))
    try:
        from src.infrastructure.browser.human_behavior import HumanBehavior
        await HumanBehavior.scroll_to_locator(page, locator, target_ratio=ratio)
    except Exception as e:
        logger.debug("物理滚动到视口异常: %s", e)

    try:
        from src.infrastructure.anti_risk.delays import random_delay

        await random_delay(page, wait_ms, metadata, config)
    except Exception:
        await page.wait_for_timeout(wait_ms)


async def _input_single_topic(
    page: Page,
    edit_box: Locator,
    label: str,
    topic_index: int,
    body_text: str,
    speed_rate: float,
) -> Tuple[str, str]:
    """输入单个话题：选建议后 Space 收成，返回 (mode, suggestion)。"""
    micro = lambda ms: _topic_pause_ms(ms, speed_rate)
    type_delay = _topic_type_delay(speed_rate)

    await edit_box.click()
    await page.keyboard.press("Control+End")
    await page.wait_for_timeout(micro(60))

    if body_text or topic_index > 0:
        await page.keyboard.type(" ")
        await page.wait_for_timeout(micro(40))

    in_compose = await _caret_in_topic_compose(page, edit_box)
    use_btn = should_use_topic_entry_btn(topic_index, in_compose)
    mode = "skip_hash"
    if use_btn:
        if await _click_topic_entry_btn_scoped(page, edit_box, speed_rate=speed_rate):
            mode = "topic_btn_first" if topic_index == 0 else "topic_btn"
            await edit_box.click()
            await page.keyboard.press("Control+End")
            await page.wait_for_timeout(micro(45))
        elif in_compose:
            mode = "skip_hash"
        else:
            await page.keyboard.type("#")
            await page.wait_for_timeout(micro(35))
            mode = "hash_prefix"
    elif in_compose:
        mode = "skip_hash"
    else:
        await page.keyboard.type("#")
        await page.wait_for_timeout(micro(35))
        mode = "hash_prefix"

    await _type_chinese_with_ime(page, label, speed_rate, type_delay)
    await page.wait_for_timeout(micro(50))
    await _fix_double_hash_before_caret(page, edit_box)
    suggestion = await _confirm_topic_when_dropdown_ready(
        page, label, speed_rate=speed_rate
    )
    return mode, suggestion


async def _type_topics_with_space_confirm(
    page: Page,
    edit_box: Locator,
    body_text: str,
    topics: List[str],
    speed_rate: float,
    metadata: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    """逐个输入话题：首话题才点按钮 → 选建议 → Space；未增加时仅重试确认（不重复输入）。"""
    if not topics:
        return

    labels = [_topic_label_for_type(t) for t in topics]
    labels = [x for x in labels if x]

    topics_norm_before = _distinct_normalized_topics(
        await _extract_topics_from_editor(page, edit_box)
    )

    for i, label in enumerate(labels):
        mode, suggestion = await _input_single_topic(
            page, edit_box, label, i, body_text, speed_rate
        )
        await page.wait_for_timeout(_topic_pause_ms(45, speed_rate))
        topics_raw = await _extract_topics_from_editor(page, edit_box)
        topics_norm = _distinct_normalized_topics(topics_raw)

        if not _topic_label_in_collected(label, topics_raw):
            count_before = len(topics_norm_before)
            count_after = len(topics_norm)
            if count_after <= count_before:
                logger.warning(
                    "话题 [%d] %s 未收录(前=%s 后=%s)，补按空格确认",
                    i + 1,
                    label,
                    topics_norm_before,
                    topics_norm,
                )
                await edit_box.click()
                await page.keyboard.press("Control+End")
                await page.wait_for_timeout(_topic_pause_ms(35, speed_rate))
                suggestion2 = await _confirm_topic_when_dropdown_ready(
                    page, label, speed_rate=speed_rate
                )
                await page.wait_for_timeout(_topic_pause_ms(40, speed_rate))
                topics_raw = await _extract_topics_from_editor(page, edit_box)
                topics_norm = _distinct_normalized_topics(topics_raw)
                mode = f"{mode}+space_retry"
                suggestion = suggestion2

        topics_norm_before = topics_norm

        logger.info(
            "话题输入 [%d/%d] label=%s mode=%s suggestion=%s topics=%d parsed=%s",
            i + 1,
            len(labels),
            label,
            mode,
            suggestion,
            len(topics_norm),
            topics_norm,
        )

    await _log_editor_topics_postcheck(page, edit_box, labels)


class MetadataFillStep(BasePublishStep):
    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        """填写元数据：标题 + 正文（含已确认的 #话题）。"""
        await self._await_pause(metadata)
        title = metadata.get("title", "") or ""
        description = metadata.get("description", "") or ""
        tags = metadata.get("tags", []) or []
        tags = (
            tags
            if isinstance(tags, list)
            else [t.strip() for t in str(tags).split(",") if t.strip()]
        )

        _log_description_topic_preprocess(description, tags)
        body_text, topics_to_type = _split_body_and_topics(description, tags)

        max_topics_cfg = 10
        try:
            from ..publish_plugin import _load_limits

            max_topics_cfg = int(_load_limits().get("max_topics", 10) or 10)
        except Exception:
            pass
        topics_to_type, truncated = _truncate_topics_to_limit(topics_to_type, max_topics_cfg)
        if truncated:
            logger.warning(
                "话题数超过平台上限，已截断为前 %d 个: %s",
                max_topics_cfg,
                _format_topics_for_log(topics_to_type),
            )
            USER_LOG.warning(
                "[步骤5 作品描述] ⚠ 话题超过 %d 个，已仅保留前 %d 个",
                max_topics_cfg,
                max_topics_cfg,
            )

        logger.info(
            "开始填写元数据: 标题=%s…, 纯正文长度=%d, 待输入话题数=%d",
            (title or "")[:20],
            len(body_text),
            len(topics_to_type),
        )

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        desc_delay = max(20, int(50 * speed_rate))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        # ── 0. 随机视线扫视 ──
        try:
            import random
            from src.infrastructure.browser.human_behavior import HumanBehavior
            vp = await page.evaluate("() => ({ w: window.innerWidth, h: window.innerHeight })")
            vw, vh = float(vp.get("w") or 800), float(vp.get("h") or 600)
            
            for _ in range(random.randint(1, 2)):
                from_x = random.uniform(vw * 0.2, vw * 0.8)
                from_y = random.uniform(vh * 0.6, vh * 0.9)
                to_x = random.uniform(vw * 0.2, vw * 0.8)
                to_y = random.uniform(vh * 0.2, vh * 0.5)
                await HumanBehavior.mouse_move(page, from_x, from_y, to_x, to_y, steps=random.randint(20, 40))
                await page.wait_for_timeout(random.randint(400, 1200))
        except Exception as e:
            logger.debug("随机视线扫视异常: %s", e)

        # ── 1. 标题 ──
        if title:
            title_text = title.strip()[:20]
            for selector in Selectors.PUBLISH["TITLE_INPUT"]:
                try:
                    title_input = page.locator(selector).first
                    if await title_input.count() > 0 and await title_input.is_visible():
                        await _scroll_locator_into_comfortable_view(
                            page, title_input, metadata, config, wait_ms=wait_ms(400)
                        )
                        logger.info("已温和滚动标题输入区入视口（顶部留白）: %s", selector)
                        
                        try:
                            import random
                            from src.infrastructure.browser.human_behavior import HumanBehavior
                            await HumanBehavior.hover_and_jitter(page, title_input, duration=random.uniform(2.0, 4.0))
                        except Exception:
                            pass

                        try:
                            from src.infrastructure.anti_risk.human_like import human_type_text

                            await human_type_text(page, selector, title_text, metadata, config)
                        except Exception:
                            await title_input.click()
                            await page.keyboard.press("Control+A")
                            await page.keyboard.press("Backspace")
                            await page.keyboard.type(
                                title_text, delay=max(10, int(30 * speed_rate))
                            )
                        logger.info("已填写标题: %s", selector)
                        t_display = (
                            title_text[:15] + "…" if len(title_text) > 15 else title_text or "（空）"
                        )
                        USER_LOG.info(f"[步骤5 作品描述] ▶ 标题已填写：{t_display}")
                        break
                except Exception:
                    continue

        if not body_text and not topics_to_type:
            logger.info("无正文与话题，跳过描述填写")
            return None

        # ── 2. 正文/描述 ──
        editor_selectors = list(Selectors.PUBLISH["DESC_EDITOR"])

        for selector in editor_selectors:
            try:
                edit_box = page.locator(selector).first
                if await edit_box.count() > 0 and await edit_box.is_visible():
                    logger.info("找到编辑器: %s", selector)

                    await _scroll_locator_into_comfortable_view(
                        page, edit_box, metadata, config, wait_ms=wait_ms(450)
                    )
                    logger.info("已温和滚动描述编辑器入视口（顶部留白，约 %.0f%%）", _SCROLL_VIEWPORT_TOP_RATIO * 100)
                    
                    try:
                        import random
                        from src.infrastructure.browser.human_behavior import HumanBehavior
                        await HumanBehavior.hover_and_jitter(page, edit_box, duration=random.uniform(2.0, 5.0))
                    except Exception:
                        pass

                    try:
                        from src.infrastructure.anti_risk.human_like import human_click

                        await human_click(page, edit_box, metadata, config)
                    except Exception:
                        await edit_box.click()

                    try:
                        from src.infrastructure.anti_risk.delays import random_delay

                        await random_delay(page, wait_ms(500), metadata, config)
                    except Exception:
                        await page.wait_for_timeout(wait_ms(500))

                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    try:
                        from src.infrastructure.anti_risk.delays import random_delay

                        await random_delay(page, wait_ms(300), metadata, config)
                    except Exception:
                        await page.wait_for_timeout(wait_ms(300))

                    # 阶段 A：纯正文
                    if body_text:
                        typed_ok = False
                        try:
                            from src.infrastructure.anti_risk.human_like import human_type_text

                            await human_type_text(
                                page,
                                selector,
                                body_text,
                                metadata,
                                config,
                                use_operation_delay=False,
                                clear_first=False,
                            )
                            typed_ok = True
                        except Exception as te:
                            logger.debug("human_type_text 正文失败，降级 keyboard.type: %s", te)
                        if not typed_ok:
                            await _type_chinese_with_ime(page, body_text, speed_rate, desc_delay)
                        logger.info("纯正文已输入，长度=%d", len(body_text))

                    # 阶段 B：逐话题 Space 收词
                    if topics_to_type:
                        USER_LOG.info(
                            "[步骤5 作品描述] ▶ 正文 %d 字，将逐个输入 %d 个话题（检测下拉后确认）",
                            len(body_text),
                            len(topics_to_type),
                        )
                        await _type_topics_with_space_confirm(
                            page,
                            edit_box,
                            body_text,
                            topics_to_type,
                            speed_rate,
                            metadata,
                            config,
                        )
                        logger.info(
                            "已逐个输入话题并按空格确认: %s",
                            _format_topics_for_log(topics_to_type),
                        )

                    try:
                        from src.infrastructure.anti_risk.delays import random_delay

                        await random_delay(page, wait_ms(400), metadata, config)
                    except Exception:
                        await page.wait_for_timeout(wait_ms(400))

                    desc_part = (description or title or "").strip()
                    desc_display = (
                        (desc_part[:35] + "…") if len(desc_part) > 35 else (desc_part or "（空）")
                    )
                    USER_LOG.info(
                        f"[步骤5 作品描述] ✓ 正文已填写：{desc_display}，已确认话题数={len(topics_to_type)}"
                    )
                    logger.info("元数据填写完成（正文+话题）")
                    return None
            except Exception as e:
                logger.warning("使用选择器 %s 填写失败: %s", selector, e)
                continue

        logger.warning("未能找到编辑器元素，跳过元数据填写")
        return None
