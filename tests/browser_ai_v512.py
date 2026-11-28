"""Real AI production components, synthetic memory-only API, no paid calls."""
import argparse,json
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--base-url',default='http://127.0.0.1:5175')
    parser.add_argument('--chromium',default='/usr/bin/chromium')
    args=parser.parse_args();base=args.base_url.rstrip('/');origin=urlsplit(base)
    if origin.scheme!='http' or origin.hostname!='127.0.0.1' or origin.path:raise ValueError('Use loopback HTTP origin')
    args.output.mkdir(parents=True,exist_ok=False)
    from playwright.sync_api import sync_playwright
    checks=[];errors=[];blocked=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        page.on('pageerror',lambda e:errors.append(str(e)))
        def guard(route):
            target=urlsplit(route.request.url)
            if target.netloc!=origin.netloc or target.path.startswith('/api/'):
                blocked.append(route.request.url);route.abort()
            else:route.continue_()
        page.route('**/*',guard);page.goto(base+'/preview-ai.html',wait_until='networkidle')
        page.get_by_role('heading',name='服务商与模型',exact=True).wait_for()
        assert page.locator('.services .service').count()==1 and page.locator('.services .model').count()==2
        assert page.get_by_role('alert').filter(has_text='默认模型已不可用').count()==1
        assert page.locator('input[type=password]').count()==0
        checks.append('production service/model UI, affected tasks, environment references')
        cjk=page.evaluate("""async()=>{await document.fonts.ready;const canvas=document.createElement('canvas');canvas.width=64;canvas.height=64;const ctx=canvas.getContext('2d');ctx.font='32px '+getComputedStyle(document.body).fontFamily;function glyph(t){ctx.clearRect(0,0,64,64);ctx.fillText(t,4,40);return Array.from(ctx.getImageData(0,0,64,64).data).join(',')}return glyph('重')!==glyph('庆')&&glyph('重')!==glyph('')}""")
        assert cjk,'CJK glyphs required for screenshot acceptance'
        for width in (1440,1024,390,320):
            page.set_viewport_size({'width':width,'height':1000})
            for mode in ('light','dark'):
                page.get_by_role('button',name='切换自定义配色',exact=True).click()
                if page.evaluate('document.documentElement.dataset.mode')!=mode:page.get_by_role('button',name='切换自定义配色',exact=True).click()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,mode)
                assert page.locator('.services .model').first.bounding_box()['width']>100
                page.screenshot(path=str(args.output/f'ai-services-{width}-{mode}.png'),full_page=True)
                checks.append(f'{width}px {mode} custom-theme geometry')
        page.set_viewport_size({'width':1440,'height':1000})
        page.get_by_role('button',name='获取模型列表',exact=True).click()
        page.get_by_label('从服务返回的模型中添加',exact=True).wait_for()
        assert page.evaluate('window.__aiPreview.lists')==1
        checks.append('explicit fixture model-list action')
        page.get_by_label('连接测试使用的内容类型',exact=True).select_option('synthetic')
        test=page.get_by_role('button',name='测试 / 核对模型连接',exact=True).first
        test.focus();test.press('Enter');modal=page.get_by_role('dialog',name='确认操作',exact=True);modal.wait_for(state='visible')
        assert modal.get_by_role('button',name='取消操作',exact=True).evaluate('el=>el===document.activeElement')
        page.keyboard.press('Escape');modal.wait_for(state='hidden')
        assert page.evaluate('window.__aiPreview.generate')==0 and test.evaluate('el=>el===document.activeElement')
        checks.append('keyboard confirmation defaults to cancel; Escape sends nothing, restores focus')
        test.click();modal.wait_for(state='visible');modal.get_by_role('button',name='确认操作',exact=True).click()
        page.get_by_role('status').filter(has_text='测试响应与格式解析成功').wait_for()
        assert page.evaluate('window.__aiPreview.generate')==1
        checks.append('explicit confirmed synthetic test and status')
        page.get_by_label('启用服务商',exact=True).uncheck();page.get_by_role('button',name='保存配置',exact=True).click()
        page.get_by_role('status').filter(has_text='配置已保存').wait_for()
        page.screenshot(path=str(args.output/'ai-disabled-service-defaults.png'),full_page=True)
        page.get_by_role('button',name='写作任务默认值',exact=True).click()
        page.get_by_role('alert').filter(has_text='当前任务默认模型不可用').wait_for()
        model=page.get_by_label('写作模型',exact=True)
        assert model.input_value()=='' and model.locator('option').count()==1
        page.get_by_role('button',name='固定选区与发送范围',exact=True).click()
        page.get_by_label('我确认将标题、展示日期、所选正文范围和素材发送给所选模型',exact=True).check()
        assert page.get_by_role('button',name='生成并预览',exact=True).is_disabled()
        assert page.evaluate('window.__aiPreview.generate')==1
        checks.append('disabled service prevents defaults and generation without fallback')
        page.set_viewport_size({'width':320,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(args.output/'ai-disabled-task-320.png'),full_page=True)
        page.get_by_role('button',name='服务商与模型管理',exact=True).click();page.get_by_label('启用服务商',exact=True).check();page.get_by_role('button',name='保存配置',exact=True).click();page.get_by_role('status').filter(has_text='配置已保存').wait_for()
        page.get_by_role('button',name='写作任务默认值',exact=True).click();model=page.get_by_label('写作模型',exact=True)
        assert model.input_value()!=''
        page.get_by_label('写作操作',exact=True).select_option('summary')
        assert model.input_value()=='' and model.locator('option').count()==2
        page.get_by_role('alert').filter(has_text='当前任务默认模型不可用').wait_for()
        assert page.evaluate('window.__aiPreview.generate')==1
        page.screenshot(path=str(args.output/'ai-missing-summary-default-320.png'),full_page=True)
        checks.append('missing task default stays empty while another model is available')
        assert not errors,errors;assert not blocked,blocked
        report={'passed':len(checks),'failed':0,'checks':checks,'screenshots':sorted(path.name for path in args.output.glob('*.png')),'browser':'Chromium','real_provider_end_to_end':'pending; synthetic protocol/browser verification only','external_or_real_api_requests':0,'page_errors':errors}
        (args.output/'browser-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False));browser.close()


if __name__=='__main__':main()
