"""v5.1.12 synthetic real-component Chromium matrix; Vite loopback 5174 only."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from browser_writing_preview import ready_media


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--chromium',default='/usr/bin/chromium')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];blocked=[];matrix=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def guard(route):
            url=urlsplit(route.request.url)
            if url.netloc!='127.0.0.1:5174' or url.path.startswith('/api/'):
                blocked.append(route.request.url);route.abort()
            else:route.continue_()
        page.route('**/*',guard);page.goto('http://127.0.0.1:5174/preview-writing.html',wait_until='networkidle')
        page.locator('.life-entry-card').first.wait_for()
        for width in (1440,1024,390,320):
            page.set_viewport_size({'width':width,'height':1000})
            for theme in ('light','dark','custom'):
                desired='dark' if theme=='dark' else 'light'
                if page.evaluate('document.documentElement.dataset.mode')!=desired:page.get_by_role('button',name='切换深色' if desired=='dark' else '切换浅色',exact=True).click()
                if theme=='custom':
                    page.get_by_role('button',name='自定义主题',exact=True).click()
                    assert page.locator('.life-entry-card').first.evaluate('el=>getComputedStyle(el).backgroundColor')=='rgb(255, 250, 255)'
                for scenario in ('full','minimal','multiline','unknown'):
                    page.get_by_label('卡片样例',exact=True).select_option(scenario);ready_media(page)
                    cards=page.locator('.preview-card-grid .life-entry-card');assert cards.count()==6
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,theme,scenario)
                    for card in cards.all():assert card.evaluate('el=>el.scrollWidth<=el.clientWidth+1'),(width,theme,scenario,card.get_attribute('data-entry-kind'))
                    route=cards.filter(has=page.locator('.transport-route'));assert 'Asia/Shanghai' not in route.inner_text()
                    assert not route.locator('.route-end p').count()
                    if scenario=='full':
                        for text in ('G8533','重庆','沙坪坝站','成都','15:43','17:36','1小时53分钟','二等座','05','08A','这次特意选了靠窗的位置，沿途的风景很不错。'):assert text in route.inner_text(),text
                    if scenario=='minimal':
                        assert not cards.locator('dl,.entry-reflection,.entry-visuals,.entry-extra').count()
                    if scenario=='multiline':
                        for card in cards.all():
                            note=card.locator('.entry-reflection p').filter(has_text='合成多行记录')
                            assert note.count()==1 and note.inner_text().count('合成多行记录')==12
                            assert '\n' in note.inner_text()
                    if scenario=='unknown':
                        assert cards.locator('.entry-extra').count()==6
                        for extra in cards.locator('.entry-extra').all():
                            extra.locator('summary').click();assert '未知历史扩展\n第二行' in extra.inner_text()
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    matrix.append({'width':width,'theme':theme,'scenario':scenario,'cards':6,'overflow':False})
                    if scenario in ('full','minimal') and width in (1440,320):page.screenshot(path=str(args.output/f'v512-{width}-{theme}-{scenario}.png'),full_page=True)
        page.get_by_label('卡片样例',exact=True).select_option('full')
        page.get_by_role('button',name='完整文章',exact=True).click()
        body=page.locator('.article-body');assert body.locator('.life-entry-card').count()==6
        assert not body.locator('.entry-menu-trigger').count()
        page.get_by_role('button',name='纯正文',exact=True).click();assert body.locator('.entry-inline').count()==6;assert not body.locator('.life-entry-card').count()
        opener=body.locator('.entry-inline').last;opener.click();dialog=body.locator('dialog[open]');assert 'G8533' in dialog.inner_text();dialog.get_by_role('button',name='关闭卡片',exact=True).click();assert opener.evaluate('el=>el===document.activeElement')
        page.get_by_role('button',name='卡片汇总',exact=True).click();assert body.locator('.summary-entry').count()==6
        page.get_by_role('button',name='交通 (1)',exact=True).click();assert body.locator('.summary-entry').count()==1
        page.get_by_role('button',name='定位至正文 · G8533',exact=True).click()
        target=body.locator('#entry-10000000-0000-4000-8000-000000000006');assert target.count()==1;assert target.evaluate('el=>el===document.activeElement')
        assert body.get_by_role('button',name='完整阅读',exact=True).get_attribute('aria-pressed')=='true'
        ready_media(page);target.scroll_into_view_if_needed()
        page.screenshot(path=str(args.output/'v512-reading-jump-320.png'),full_page=True)
        # A canceled shortcut dialog must leave the actual editor and command intact.
        page.get_by_role('button',name='日常与旅行写作',exact=True).click();page.get_by_role('button',name='新建记录',exact=True).click();page.get_by_role('button',name='正文编辑',exact=True).click()
        prose=page.locator('.immersive-prose');prose.fill('合成开头 @f');prose.press('End');prose.press('ArrowLeft');prose.press('ArrowRight')
        page.get_by_role('option',name='@f 插入美食卡片',exact=True).wait_for();prose.press('Enter')
        dialog=page.locator('dialog.entry-dialog[open]');assert dialog.get_by_label('记录类型',exact=True).input_value()=='f';dialog.get_by_role('button',name='取消',exact=True).click();assert prose.inner_text().strip()=='合成开头 @f'
        page.get_by_role('button',name='Markdown 源码',exact=True).click();source=page.locator('.body-editor textarea:visible').first;assert '合成开头 @f' in source.input_value()
        source.fill('合成源码 @t');source.press('End');source.press('ArrowLeft');source.press('ArrowRight');page.get_by_role('option',name='@t 插入交通卡片',exact=True).wait_for();source.press('Enter')
        dialog=page.locator('dialog.entry-dialog[open]');assert dialog.get_by_label('记录类型',exact=True).input_value()=='t';dialog.get_by_role('button',name='取消',exact=True).click();assert source.input_value()=='合成源码 @t'
        assert not blocked,blocked;assert not errors,errors
        result={'browser':browser.version,'matrix':matrix,'reading_modes_filter_uuid_jump':True,'visual_and_source_shortcut_cancel_preserves_command':True,'actual_network_requests':0,'errors':errors,'screenshots':sorted(f.name for f in args.output.glob('*.png'))}
        (args.output/'browser-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2));browser.close()


if __name__=='__main__':main()
