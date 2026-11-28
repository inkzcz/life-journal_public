"""Optional Linux/Chromium fixture preview checks; never real accounts or API.

Requires existing Playwright + Chromium, and Vite on loopback port 5174. Screenshots
are synthetic, outside the source tree. This is not a Windows/NAS acceptance test.
"""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


def ready_media(page):
    for card in page.locator('.life-entry-card').all():card.scroll_into_view_if_needed()
    page.wait_for_function("document.querySelectorAll('.entry-visuals .private-image-status:not(.image-unavailable)').length===0")
    page.wait_for_function("Array.from(document.querySelectorAll('.entry-visuals img')).every(i=>i.complete&&i.naturalWidth>0)")
    page.evaluate('scrollTo(0,0)')


def exercise_cards(page):
    prose=page.locator('.immersive-prose');original=prose.inner_text().strip();identities={}
    for index,kind in enumerate(('l','f','m','s','g','t'),1):
        print('Creating and editing synthetic card '+kind,flush=True)
        prose.focus();prose.press('Control+End');prose.press('Enter')
        page.locator('[role=toolbar]').get_by_role('button',name='插入卡片',exact=True).click()
        dialog=page.locator('dialog.entry-dialog[open]')
        dialog.get_by_label('记录类型',exact=True).select_option(kind)
        dialog.locator('input[required][maxlength="200"]').fill('合成卡片-'+str(index))
        if kind!='t' and dialog.locator('input[type=date]').count():dialog.locator('input[type=date]').first.fill('2026-11-22')
        if kind=='t':
            dialog.get_by_label('出发日期',exact=True).fill('2026-11-13')
            dialog.get_by_label('出发时间',exact=True).fill('15:43')
            dialog.get_by_label('到达日期',exact=True).fill('2026-11-13')
            dialog.get_by_label('到达时间',exact=True).fill('17:36')
            dialog.get_by_label('到达时间',exact=True).press('Tab')
            assert '1小时53分钟' in dialog.inner_text()

        dialog.get_by_role('button',name='插入卡片',exact=True).click()
        node=page.locator('.entry-card').filter(has_text='合成卡片-'+str(index))
        node.wait_for();identity=node.get_attribute('id')
        assert node.bounding_box()['width']>80
        node.get_by_role('button',name='卡片操作',exact=True).click()
        page.get_by_role('menuitem',name='编辑卡片',exact=True).click()
        node.locator('form input[required][maxlength="200"]').fill('编辑后卡片-'+str(index))
        node.get_by_role('button',name='保存卡片',exact=True).click()
        assert page.locator('.entry-card').filter(has_text='编辑后卡片-'+str(index)).get_attribute('id')==identity
        identities[kind]=identity.removeprefix('entry-')
    # A draft in card A must block transferring clean card B: a successful
    # transfer reloads the whole document, not just the selected NodeView.
    print('Checking actual card actions and draft protection',flush=True)
    first=page.locator('.entry-card').first
    first.get_by_role('button',name='卡片操作',exact=True).click()
    page.get_by_role('menuitem',name='编辑卡片',exact=True).click()
    draft=first.locator('form input[required][maxlength="200"]')
    draft.fill('合成未保存的卡片草稿')
    page.get_by_role('button',name='Markdown 源码',exact=True).click()
    assert page.locator('.immersive-prose').is_visible()
    assert draft.input_value()=='合成未保存的卡片草稿'
    second=page.locator('.entry-card').nth(1)
    for action in ('复制到其他文章','移动到其他文章'):
        second.get_by_role('button',name='卡片操作',exact=True).click()
        page.get_by_role('menuitem',name=action,exact=True).click()
        second.get_by_role('status').filter(has_text='请先保存或取消其他卡片编辑').wait_for()
        assert not page.locator('.entry-target-picker[open]').count()
        assert draft.input_value()=='合成未保存的卡片草稿'
    first.get_by_role('button',name='取消',exact=True).click()
    # Native menu actions operate on actual ProseMirror nodes, not preview markup.
    first=page.locator('.entry-card').first
    first.get_by_role('button',name='卡片操作',exact=True).click()
    menu=page.get_by_role('menu')
    menu.get_by_role('menuitem',name='复制卡片',exact=True).click()
    assert page.locator('.entry-card').count()==7
    page.wait_for_function("new Set(Array.from(document.querySelectorAll('.entry-card'),el=>el.id)).size===7")
    duplicate=page.locator('.entry-card').nth(1);duplicate_id=duplicate.get_attribute('id')
    assert duplicate_id not in ('entry-'+value for value in identities.values()), {'cards':[(el.get_attribute('id'),el.inner_text()[:35]) for el in page.locator('.entry-card').all()],'original':identities}
    before=duplicate.evaluate('el=>Array.from(el.parentElement.children).indexOf(el)')
    duplicate.get_by_role('button',name='卡片操作',exact=True).click()
    page.get_by_role('menuitem',name='向下移动',exact=True).click()
    page.wait_for_function('(p)=>{const el=document.getElementById(p.id);return el&&Array.from(el.parentElement.children).indexOf(el)===p.position}',arg={'id':duplicate_id,'position':before+1})
    duplicate=page.locator('[id="'+duplicate_id+'"]')
    duplicate.get_by_role('button',name='卡片操作',exact=True).click()
    page.get_by_role('menuitem',name='向上移动',exact=True).click()
    page.wait_for_function('(p)=>{const el=document.getElementById(p.id);return el&&Array.from(el.parentElement.children).indexOf(el)===p.position}',arg={'id':duplicate_id,'position':before})
    duplicate.get_by_role('button',name='卡片操作',exact=True).click()
    page.once('dialog',lambda dialog:dialog.accept())
    page.get_by_role('menuitem',name='删除卡片',exact=True).click()
    assert page.locator('.entry-card').count()==6
    page.locator('.entry-card').first.get_by_role('button',name='卡片操作',exact=True).click()
    page.once('dialog',lambda dialog:dialog.accept())
    page.get_by_role('menuitem',name='复制到其他文章',exact=True).click()
    picker=page.locator('.entry-target-picker[open]');picker.wait_for()
    picker.get_by_label('搜索文章标题').fill('合成')
    picker.get_by_role('button',name='搜索最近编辑文章').click()
    picker.locator('input[type=radio]').check()
    assert picker.get_by_role('button',name='确认复制').is_enabled()
    picker.get_by_role('button',name='取消',exact=True).click()
    assert not picker.count()
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
        page.set_default_timeout(15000)
        errors=[];blocked=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def guard(route):
            target=urlsplit(route.request.url)
            if target.netloc!='127.0.0.1:5174' or target.path.startswith('/api/'):
                blocked.append('unexpected network request');route.abort()
            else:route.continue_()
        page.route('**/*',guard)
        page.goto('http://127.0.0.1:5174/preview-writing.html',wait_until='networkidle')
        # Missing CJK fonts can satisfy DOM geometry while screenshots contain
        # only identical tofu boxes. Check actual rendered pixels, not font names.
        cjk=page.evaluate("""async()=>{await document.fonts.ready;
            const canvas=document.createElement('canvas');canvas.width=64;canvas.height=64;
            const ctx=canvas.getContext('2d');ctx.font='32px '+getComputedStyle(document.body).fontFamily;
            function glyph(text){ctx.clearRect(0,0,64,64);ctx.fillText(text,4,40);return Array.from(ctx.getImageData(0,0,64,64).data).join(',')}
            const empty=glyph(''),chong=glyph('重'),qing=glyph('庆');
            return chong!==empty&&qing!==empty&&chong!==qing;
        }""")
        assert cjk, 'CJK glyphs missing: install runner fonts before visual acceptance; identical tofu is not a pass'
        page.locator('.life-entry-card').first.wait_for()
        assert page.locator('.life-entry-card').count()==6
        page.locator('.entry-visuals img').first.wait_for()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        ready_media(page)
        geometry=[]
        for width in (1440,1360,1024,768,390,375,320):
            page.set_viewport_size({'width':width,'height':1000})
            for dark in (False,True):
                desired='dark' if dark else 'light'
                if page.evaluate('document.documentElement.dataset.mode')!=desired:page.get_by_role('button',name='切换深色' if dark else '切换浅色',exact=True).click()
                page.wait_for_function("document.documentElement.dataset.mode==='"+desired+"'")
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,desired)
                route=page.locator('[data-entry-kind=t]')
                for text in ('G8533','15:43','17:36','重庆','成都','1小时53分钟'):assert text in route.inner_text()
                start=route.locator('.route-start').bounding_box();center=route.locator('.route-connection').bounding_box();end=route.locator('.route-end').bounding_box()
                assert start['x']+start['width']<=center['x']+1 and center['x']+center['width']<=end['x']+1,(width,start,center,end)
                assert not route.locator('.route-end p').count(),'Unconfirmed arrival station was invented'
                for card in page.locator('.life-entry-card').all():assert card.evaluate('el=>el.scrollWidth<=el.clientWidth+1')
                geometry.append({'viewport':width,'mode':desired,'start':start,'connection':center,'end':end})
                if width in (1440,375,320):page.screenshot(path=str(args.output/f'cards-{width}-{desired}.png'),full_page=True)
        (args.output/'geometry.json').write_text(json.dumps(geometry,indent=2)+'\n')
        page.get_by_role('button',name='自定义主题',exact=True).click()
        page.wait_for_function("document.documentElement.dataset.palette==='lilac'")
        assert page.locator('.life-entry-card').first.evaluate('el=>getComputedStyle(el).backgroundColor')=='rgb(48, 42, 56)'
        page.screenshot(path=str(args.output/'cards-custom-theme.png'),full_page=True)
        for media in ('none','multiple','unavailable','normal'):
            page.get_by_label('媒体验收',exact=True).select_option(media)
            if media=='none':assert page.locator('.entry-visuals').count()==0
            if media=='multiple':assert page.locator('.entry-photo-count').count()==6
            if media=='unavailable':page.locator('.image-unavailable').first.wait_for()
            ready_media(page)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            if media!='normal':page.screenshot(path=str(args.output/f'media-{media}.png'),full_page=True)
        page.get_by_role('button',name='完整文章',exact=True).click()
        assert page.locator('.article-body .life-entry-card').count()==6
        assert page.locator('.article-body .entry-menu-trigger').count()==0
        for card in page.locator('.article-body .life-entry-card').all():card.scroll_into_view_if_needed()
        page.wait_for_function("document.querySelectorAll('.article-body .private-image-status').length===0")
        page.evaluate('scrollTo(0,0)')
        page.locator('.article-body .entry-visuals img').first.wait_for()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(args.output/'article-mobile.png'),full_page=True)
        page.locator('.article-body .body-photo-button').first.click()
        page.locator('dialog[open]').get_by_role('button',name='关闭图片',exact=True).click()
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
        print('Starting actual editor card workflow',flush=True)
        exercise_cards(page)
        page.screenshot(path=str(args.output/'writing-cards-desktop.png'),full_page=True)
        for width in (390,375,320):
            page.set_viewport_size({'width':width,'height':812})
            transport=page.locator('.entry-card').last
            assert transport.bounding_box()['width']>=min(width-80,240)
            for stamp in transport.locator('.route-time').all():
                assert stamp.evaluate('el=>el.getBoundingClientRect().height<=parseFloat(getComputedStyle(el).fontSize)*1.3'),'Transport clock wrapped in the actual editor'
            transport.get_by_role('button',name='卡片操作',exact=True).click()
            menu=page.get_by_role('menu');rect=menu.bounding_box()
            assert rect['x']>=0 and rect['x']+rect['width']<=width
            if width==320:page.screenshot(path=str(args.output/'editor-menu-320.png'))
            menu.get_by_role('menuitem',name='编辑卡片',exact=True).click()
            form=transport.locator('form');form.get_by_label('出发日期',exact=True).wait_for()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert form.locator('.transport-time-fields').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
            assert form.get_by_label('出发日期',exact=True).bounding_box()['width']>=130
            if width==320:form.screenshot(path=str(args.output/'editor-time-form-320.png'))
            form.get_by_role('button',name='取消',exact=True).click()
        page.set_viewport_size({'width':375,'height':812})
        page.get_by_role('button',name='通知配置',exact=True).click()
        field=page.get_by_label('通知 URL 模板',exact=True)
        field.wait_for();assert field.get_attribute('type')=='text'
        assert 'SPT_SYNTHETIC_ONLY' in field.input_value()
        field.fill('https://notify.example.invalid/'+('synthetic-segment/'*150)+'{content}')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.get_by_label('请求方式',exact=True).select_option('POST')
        page.get_by_role('button',name='添加请求头',exact=True).click()
        header=page.get_by_label('请求头值',exact=True)
        assert header.get_attribute('type')=='password'
        header.fill('synthetic-header-only')
        page.get_by_role('button',name='查看 / 编辑请求体',exact=True).click()
        page.get_by_label('请求体模板',exact=True).fill('\x7b"message":{"title":"{title}","content":"{content}"},"items":[1,true,null]\x7d')
        page.get_by_role('button',name='隐藏请求体',exact=True).click()
        assert not page.get_by_label('请求体模板',exact=True).count()
        page.get_by_role('button',name='预览请求（不发送）',exact=True).click()
        page.get_by_label('脱敏请求预览',exact=True).wait_for()
        assert 'synthetic-header-only' not in page.get_by_label('脱敏请求预览',exact=True).inner_text()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(args.output/'notification-mobile.png'),full_page=True)
        assert not blocked, 'Preview attempted unexpected network access'
        assert not errors, errors
        result={'browser':browser.version,'cjk_glyphs_present':cjk,'platform':'Linux headless Chromium','cards':6,
            'responsive_geometry_matrix':geometry,'desktop_and_mobile':True,'light_and_dark':True,'no_horizontal_overflow':True,
            'new_daily_and_travel_controls':True,'mode_switch_keeps_body_and_title':True,
            'six_kinds_created_and_edited_through_actual_forms':True,'card_uuid_and_source_visual_roundtrip_preserved':True,'other_card_draft_blocks_copy_move_and_mode_switch':True,
            'mobile_editor_clock_form_and_menu_widths':[390,375,320],'visible_long_notification_url':True,'actual_api_or_external_requests':0,'page_errors':errors,
            'images':sorted(path.name for path in args.output.glob('*.png'))}
        (args.output/'browser-results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2));browser.close()


if __name__=='__main__':main()
