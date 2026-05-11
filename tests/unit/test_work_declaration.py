"""domain.publish.work_declaration 单元测试"""
import json

from src.domain.publish.work_declaration import (
    KEY_DOUYIN,
    KEY_DOUYIN_AUTO,
    KEY_IS_ORIGINAL,
    KEY_KUAISHOU,
    KEY_KUAISHOU_AUTO,
    KEY_XHS_CONTENT_ATTR,
    KEY_XHS_CONTENT_ATTR_AUTO,
    KEY_XHS_ORIGINAL,
    XHS_ATTR_MARKETING,
    DOUYIN_AI_GENERATED,
    DOUYIN_NONE,
    DOUYIN_OPINION,
    declaration_auto_apply,
    douyin_declaration_click_texts,
    format_work_declaration_table_cell,
    format_work_declaration_preview_cell,
    strip_privacy_declaration_keys_for_platform,
)


def test_format_wechat():
    ps = json.dumps({KEY_IS_ORIGINAL: True})
    assert format_work_declaration_table_cell("wechat_video", ps) == "申明原创"
    ps2 = json.dumps({KEY_IS_ORIGINAL: False})
    assert format_work_declaration_table_cell("wechat_video", ps2) == "—"


def test_preview_account_group_skips_wechat_when_not_original():
    ps = {KEY_IS_ORIGINAL: False, KEY_DOUYIN: DOUYIN_AI_GENERATED, KEY_DOUYIN_AUTO: True}
    s = format_work_declaration_preview_cell(
        "account_group",
        ps,
        account_group_includes_wechat=True,
        account_group_includes_douyin=True,
    )
    assert "视频号" not in s
    assert "抖音" in s


def test_format_douyin():
    ps = json.dumps({KEY_DOUYIN: DOUYIN_AI_GENERATED, KEY_DOUYIN_AUTO: True})
    assert "AI" in format_work_declaration_table_cell("douyin", ps)


def test_douyin_declaration_click_texts_matches_canonical():
    assert douyin_declaration_click_texts(DOUYIN_AI_GENERATED) == (
        "内容由AI生成",
        "内容由 AI 生成",
    )
    assert douyin_declaration_click_texts(DOUYIN_OPINION)[0] == "内容为个人观点或见解"
    assert douyin_declaration_click_texts(DOUYIN_NONE)[:2] == ("无需添加自主声明", "无需添加自主申明")


def test_format_douyin_auto_off_empty():
    ps = json.dumps({KEY_DOUYIN: DOUYIN_AI_GENERATED, KEY_DOUYIN_AUTO: False})
    assert format_work_declaration_table_cell("douyin", ps) == "—"


def test_format_kuaishou_auto_off_empty():
    ps = json.dumps({
        KEY_KUAISHOU: "ai_generated",
        KEY_KUAISHOU_AUTO: False,
    })
    assert format_work_declaration_table_cell("kuaishou", ps) == "—"


def test_format_xiaohongshu():
    ps = json.dumps({
        KEY_XHS_ORIGINAL: True,
        KEY_XHS_CONTENT_ATTR: XHS_ATTR_MARKETING,
        KEY_XHS_CONTENT_ATTR_AUTO: True,
    })
    s = format_work_declaration_table_cell("xiaohongshu", ps)
    assert "申明原创" in s
    assert "营销" in s

    ps2 = json.dumps(
        {
            KEY_XHS_ORIGINAL: False,
            KEY_XHS_CONTENT_ATTR: "",
            KEY_XHS_CONTENT_ATTR_AUTO: True,
        }
    )
    assert "不申明原创" in format_work_declaration_table_cell("xiaohongshu", ps2)

    ps3 = json.dumps({
        KEY_XHS_ORIGINAL: True,
        KEY_XHS_CONTENT_ATTR: XHS_ATTR_MARKETING,
        KEY_XHS_CONTENT_ATTR_AUTO: False,
    })
    assert format_work_declaration_table_cell("xiaohongshu", ps3) == "—"


def test_preview_account_group_skips_xhs_when_attr_auto_off():
    ps = {
        KEY_XHS_ORIGINAL: True,
        KEY_XHS_CONTENT_ATTR: XHS_ATTR_MARKETING,
        KEY_XHS_CONTENT_ATTR_AUTO: False,
    }
    s = format_work_declaration_preview_cell(
        "account_group",
        ps,
        account_group_includes_xiaohongshu=True,
    )
    assert s == "—"


def test_preview_account_group_skips_douyin_when_auto_off():
    ps = {
        KEY_DOUYIN: DOUYIN_AI_GENERATED,
        KEY_DOUYIN_AUTO: False,
        KEY_IS_ORIGINAL: True,
    }
    s = format_work_declaration_preview_cell(
        "account_group",
        ps,
        account_group_includes_wechat=True,
        account_group_includes_douyin=True,
    )
    assert "抖音" not in s
    assert "视频号" in s


def test_preview_account_group_includes_xhs():
    ps = {
        KEY_XHS_ORIGINAL: True,
        KEY_XHS_CONTENT_ATTR: XHS_ATTR_MARKETING,
        KEY_XHS_CONTENT_ATTR_AUTO: True,
    }
    s = format_work_declaration_preview_cell(
        "account_group",
        ps,
        account_group_includes_xiaohongshu=True,
    )
    assert "小红书" in s and "营销" in s


def test_strip_removes_foreign_keys():
    raw = json.dumps({
        KEY_IS_ORIGINAL: True,
        KEY_DOUYIN: "fiction",
        KEY_KUAISHOU: "ai_generated",
        KEY_DOUYIN_AUTO: True,
        KEY_KUAISHOU_AUTO: False,
        KEY_XHS_ORIGINAL: True,
        KEY_XHS_CONTENT_ATTR: "marketing",
        KEY_XHS_CONTENT_ATTR_AUTO: False,
    })
    out = json.loads(strip_privacy_declaration_keys_for_platform(raw, "douyin"))
    assert KEY_DOUYIN in out
    assert KEY_DOUYIN_AUTO in out
    assert KEY_IS_ORIGINAL not in out
    assert KEY_KUAISHOU not in out
    assert KEY_KUAISHOU_AUTO not in out
    assert KEY_XHS_ORIGINAL not in out
    assert KEY_XHS_CONTENT_ATTR not in out
    assert KEY_XHS_CONTENT_ATTR_AUTO not in out


def test_strip_xiaohongshu_keeps_xhs_keys():
    raw = json.dumps({
        KEY_IS_ORIGINAL: True,
        KEY_DOUYIN: "none",
        KEY_XHS_ORIGINAL: False,
        KEY_XHS_CONTENT_ATTR: "ai_synthesis",
        KEY_XHS_CONTENT_ATTR_AUTO: True,
    })
    out = json.loads(strip_privacy_declaration_keys_for_platform(raw, "xiaohongshu"))
    assert out.get(KEY_XHS_ORIGINAL) is False
    assert out.get(KEY_XHS_CONTENT_ATTR) == "ai_synthesis"
    assert out.get(KEY_XHS_CONTENT_ATTR_AUTO) is True
    assert KEY_IS_ORIGINAL not in out
    assert KEY_DOUYIN not in out


def test_declaration_auto_apply():
    assert declaration_auto_apply({KEY_DOUYIN_AUTO: False}, KEY_DOUYIN_AUTO) is False
    assert declaration_auto_apply({}, KEY_DOUYIN_AUTO) is False
    assert declaration_auto_apply({KEY_DOUYIN_AUTO: True}, KEY_DOUYIN_AUTO) is True

