import pytest

from src.plugins.community.douyin.steps.step_07a_music import SelectMusicStep
from tests.helpers.playwright_env import playwright_page_or_skip


MUSIC_HTML = """
<!doctype html>
<html>
  <body>
    <div class="semi-sidesheet music-side-sheet-CVkGta semi-sidesheet-right" style="width: 448px">
      <div class="semi-sidesheet-inner semi-sidesheet-inner-wrap" role="sidesheet" style="width: 448px">
        <div class="semi-sidesheet-header">
          <div class="semi-sidesheet-title">选择音乐</div>
        </div>
        <div class="semi-sidesheet-body">
          <div class="semi-tabs-tab semi-tabs-tab-active" role="tab">推荐</div>
          <div class="semi-tabs-tab" role="tab">热门榜</div>
          <div class="semi-tabs-pane-active semi-tabs-pane" role="tab-panel">
            <div class="card-container-tmocjc card-container-active-MXJa5C" style="width: 400px; height: 69px">
              <div class="card-wrapper-JTleG1">
                <div>人间小美好(治愈版)（剪辑版）</div>
                <div>佳小忆</div>
                <div>00:31</div>
                <div class="user-count-ZMh4uY">91.5万人使用</div>
                <button class="semi-button semi-button-primary apply-btn-LUPP0D">
                  <span class="semi-button-content">使用</span>
                </button>
              </div>
            </div>
            <div class="card-container-tmocjc" style="width: 400px; height: 69px">
              <div class="card-wrapper-JTleG1">
                <div>Sub Title</div>
                <div>Various Artists</div>
                <div>01:57</div>
                <div class="user-count-ZMh4uY">37.3万人使用</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
"""


@pytest.fixture
async def page():
    async with playwright_page_or_skip(viewport={"width": 1440, "height": 1000}) as page:
        yield page


@pytest.mark.asyncio
async def test_music_sidesheet_without_search_input_is_open(page):
    await page.set_content(MUSIC_HTML)

    step = SelectMusicStep()

    assert await step._is_drawer_open(page) is True


@pytest.mark.asyncio
async def test_music_card_rows_are_detected(page):
    await page.set_content(MUSIC_HTML)

    step = SelectMusicStep()
    rows = await step._get_music_rows(page)

    texts = [await row.inner_text() for row in rows]
    assert len(rows) == 2
    assert any("人间小美好" in text for text in texts)
    assert any("Sub Title" in text for text in texts)


@pytest.mark.asyncio
async def test_find_use_btn_prefers_exact_button_not_usage_text(page):
    await page.set_content(MUSIC_HTML)

    step = SelectMusicStep()
    root = await step._music_drawer_root(page)
    btn = await step._find_use_btn(root)

    assert btn is not None
    assert (await btn.inner_text()).strip() == "使用"
    assert "apply-btn" in ((await btn.get_attribute("class")) or "")


@pytest.mark.asyncio
async def test_usage_count_text_is_not_treated_as_use_button(page):
    await page.set_content(
        """
        <div class="semi-sidesheet-inner" role="sidesheet">
          <div>选择音乐</div>
          <div role="tab">推荐</div>
          <div role="tab">热门榜</div>
          <div class="card-container-tmocjc">
            <div>只有用量</div><div>00:31</div><div>91.5万人使用</div>
          </div>
        </div>
        """
    )

    step = SelectMusicStep()
    root = await step._music_drawer_root(page)

    assert await step._find_use_btn(root) is None


@pytest.mark.asyncio
async def test_activate_row_clicks_use_inside_sidesheet_only(page):
    await page.set_content(
        """
        <button id="outer-use" onclick="document.body.dataset.outerClicked='1'">使用</button>
        <div class="semi-sidesheet-inner" role="sidesheet" style="width: 448px">
          <div>选择音乐</div>
          <div role="tab">推荐</div>
          <div role="tab">热门榜</div>
          <div class="card-container-tmocjc" style="width: 400px; height: 69px">
            <div>当前可见歌曲</div><div>00:31</div><div>91.5万人使用</div>
            <button class="apply-btn-LUPP0D" onclick="document.body.dataset.innerClicked='1'">使用</button>
          </div>
        </div>
        """
    )

    step = SelectMusicStep()
    rows = await step._get_music_row_infos(page)

    assert rows
    assert await step._activate_row_and_click_use_js(page, rows[0], 1000) is True
    assert await page.evaluate("document.body.dataset.innerClicked") == "1"
    assert await page.evaluate("document.body.dataset.outerClicked") is None


@pytest.mark.asyncio
async def test_hover_row_clicks_use_button(page):
    await page.set_content(
        """
        <div class="semi-sidesheet-inner" role="sidesheet" style="width: 448px">
          <div>选择音乐</div>
          <div role="tab">推荐</div>
          <div role="tab">热门榜</div>
          <div class="card-container-tmocjc" style="width: 400px; height: 69px"
               onmouseenter="this.querySelector('button').style.display='block'">
            <div>Hover 歌曲</div><div>00:31</div><div>91.5万人使用</div>
            <button class="apply-btn-LUPP0D" style="display:none"
                    onclick="document.body.dataset.used='1'">使用</button>
          </div>
        </div>
        """
    )

    step = SelectMusicStep()

    assert await step._hover_random_music_and_click_use(page, {"music_use_hover_ms": 100}, is_random=False)
    assert await page.evaluate("document.body.dataset.used") == "1"


@pytest.mark.asyncio
async def test_specific_music_without_search_returns_none_when_no_match(page):
    await page.set_content(MUSIC_HTML)

    step = SelectMusicStep()

    assert await step._fill_search(page, "不存在的歌") is False
    assert await step._pick_row(page, is_random=False, name_filter="不存在的歌") is None


@pytest.mark.asyncio
async def test_music_rows_outside_viewport_are_ignored(page):
    await page.set_content(
        """
        <div class="semi-sidesheet-inner" role="sidesheet" style="width: 448px">
          <div>选择音乐</div>
          <div role="tab">推荐</div>
          <div role="tab">热门榜</div>
          <div class="card-container-tmocjc" style="width: 400px; height: 69px">
            <div>当前可见歌曲</div><div>00:31</div><div>91.5万人使用</div>
          </div>
          <div class="card-container-tmocjc" style="width: 400px; height: 69px; margin-top: 1200px">
            <div>视口外歌曲</div><div>01:57</div><div>37.3万人使用</div>
          </div>
        </div>
        """
    )

    step = SelectMusicStep()
    rows = await step._get_music_rows(page)
    texts = [await row.inner_text() for row in rows]

    assert len(rows) == 1
    assert "当前可见歌曲" in texts[0]


@pytest.mark.asyncio
async def test_music_module_absent_when_extension_card_has_no_music_row(page):
    await page.set_content(
        """
        <div style="width: 600px; min-height: 180px">
          <div>扩展信息</div>
          <div>添加标签</div>
          <div>游戏手柄</div>
          <div>添加作品同款游戏</div>
          <div>关联热点</div>
        </div>
        """
    )

    step = SelectMusicStep()

    assert await step._is_music_module_absent(page) is True


def test_music_row_key_ignores_duration_and_usage_count():
    text = "Sub Title\nVarious Artists\n01:57\n37.9万人使用"

    assert SelectMusicStep._music_row_key(text) == "Sub Title Various Artists"
