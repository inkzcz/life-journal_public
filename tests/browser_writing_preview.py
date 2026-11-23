"""Optional Linux/Chromium fixture preview checks; never real accounts or API.

Requires existing Playwright + Chromium, and Vite on loopback port 5174. Screenshots
are synthetic, outside the source tree. This is not a Windows/NAS acceptance test.
"""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


def exercise_cards(page):
    prose=page.locator('.immersive-prose');original=prose.inner_text().strip();identities={}
    for index,kind in enumerate(('l','f','m','s','g','t'),1):
        prose.focus();prose.press('Control+End');prose.press('Enter')
        page.get_by_role('button',name='@ 结构化记录',exact=True).click()
        dialog=page.locator('dialog.entry-dialog[open]')
        dialog.get_by_label('记录类型',exact=True).select_option(kind)
        dialog.locator('input[required][maxlength="200"]').fill('合成卡片-'+str(index))
        if dialog.locator('input[type=date]').count():dialog.locator('input[type=date]').first.fill('2026-11-22')
        dialog.get_by_role('button',name='插入卡片',exact=True).click()
        node=page.locator('.entry-card').filter(has_text='合成卡片-'+str(index))
        node.wait_for();identity=node.get_attribute('id')
        assert node.bounding_box()['width']>80
        node.get_by_role('button',name='编辑卡片',exact=True).click()
        node.locator('form input[required][maxlength="200"]').fill('编辑后卡片-'+str(index))
        node.get_by_role('button',name='保存卡片',exact=True).click()
        assert page.locator('.entry-card').filter(has_text='编辑后卡片-'+str(index)).get_attribute('id')==identity
        identities[kind]=identity.removeprefix('entry-')
    page.get_by_role('button',name='Markdown 源码',exact=True).click()
    source=page.locator('.body-editor textarea:visible').first.input_value()
    def parse(value):return [json.loads(m) for m in re.findall(r':::lj-entry-v1\r?\n([^\r\n]+)\r?\n:::',value)]
    entries=parse(source)
    assert len(entries)==6 and {e['kind']:e['id'] for e in entries}==identities
    assert all(e['name'].startswith('编辑后卡片-') for e in entries) and original in source
    page.get_by_role('button',name='可视化编辑',exact=True).click()
    assert page.locator('.entry-card').count()==6
    page.get_by_role('button',name='Markdown 源码',exact=True).click()
    assert parse(page.locator('.body-editor textarea:visible').first.input_value())==entries
    page.get_by_role('button',name='可视化编辑',exact=True).click()
    assert page.locator('.entry-card').count()==6


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--chromium',default='/usr/bin/chromium')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        errors=[];blocked=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def guard(route):
            target=urlsplit(route.request.url)
            if target.netloc!='127.0.0.1:5174' or target.path.startswith('/api/'):
                blocked.append('unexpected network request');route.abort()
            else:route.continue_()
        page.route('**/*',guard)
        page.goto('http://127.0.0.1:5174/preview-writing.html',wait_until='networkidle')
        page.locator('.life-entry-card').first.wait_for()
        assert page.locator('.life-entry-card').count()==6
        page.locator('.entry-visuals img').first.wait_for()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(args.output/'cards-desktop-light.png'),full_page=True)
        page.get_by_role('button',name='切换深色',exact=True).click()
        page.wait_for_function("document.documentElement.dataset.mode==='dark'")
        page.screenshot(path=str(args.output/'cards-desktop-dark.png'),full_page=True)
        page.set_viewport_size({'width':375,'height':812})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(args.output/'cards-mobile-dark.png'),full_page=True)
        page.get_by_role('button',name='切换浅色',exact=True).click()
        page.screenshot(path=str(args.output/'cards-mobile-light.png'),full_page=True)
        page.get_by_role('button',name='日常与旅行写作',exact=True).click()
        page.locator('.new-record').wait_for()
        assert page.locator('.new-record input[value=daily]').is_checked()
        page.locator('.new-record input[value=travel]').check()
        page.get_by_role('button',name='新建记录',exact=True).click()
        page.locator('.article-mode input[value=travel]').wait_for()
        assert page.locator('.article-mode input[value=travel]').is_checked()
        page.get_by_label('记录标题',exact=True).fill('合成旅行草稿')
        page.get_by_role('button',name='正文编辑',exact=True).click()
        page.locator('.immersive-prose').fill('模式切换后仍然保留的合成正文。')
        page.get_by_role('button',name='基本信息',exact=True).click()
        page.locator('.article-mode input[value=daily]').check()
        assert page.get_by_label('记录标题',exact=True).input_value()=='合成旅行草稿'
        page.get_by_role('button',name='正文编辑',exact=True).click()
        assert '模式切换后仍然保留的合成正文。' in page.locator('.immersive-prose').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(args.output/'writing-mobile.png'),full_page=True)
        page.set_viewport_size({'width':1360,'height':1000})
        exercise_cards(page)
        page.screenshot(path=str(args.output/'writing-cards-desktop.png'),full_page=True)
        page.set_viewport_size({'width':375,'height':812})
        page.get_by_role('button',name='通知配置',exact=True).click()
        field=page.get_by_label('通知 URL 模板',exact=True)
        field.wait_for();assert field.get_attribute('type')=='text'
        assert 'SPT_SYNTHETIC_ONLY' in field.input_value()
        field.fill('https://notify.example.invalid/'+('synthetic-segment/'*150)+'{content}')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(args.output/'notification-mobile.png'),full_page=True)
        assert not blocked, 'Preview attempted unexpected network access'
        assert not errors, errors
        result={'browser':browser.version,'platform':'Linux headless Chromium','cards':6,
            'desktop_and_mobile':True,'light_and_dark':True,'no_horizontal_overflow':True,
            'new_daily_and_travel_controls':True,'mode_switch_keeps_body_and_title':True,
            'six_kinds_created_and_edited_through_actual_forms':True,'card_uuid_and_source_visual_roundtrip_preserved':True,
            'visible_long_notification_url':True,'actual_api_or_external_requests':0,'page_errors':errors,
            'images':sorted(path.name for path in args.output.glob('*.png'))}
        (args.output/'browser-results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2));browser.close()


if __name__=='__main__':main()
