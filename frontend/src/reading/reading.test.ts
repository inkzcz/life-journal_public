// @vitest-environment jsdom
import { it,expect,vi,afterEach } from 'vitest'
import { createApp,h,nextTick } from 'vue'
import { articleMarkdown } from './markdown'
import { readingProgress,currentHeading } from './tracking'
import ArticleReader from './ArticleReader.vue'
import ArticleBody from './ArticleBody.vue'
import AdjacentPosts from './AdjacentPosts.vue'
it('creates stable unique safe anchors from Chinese, English, repeated and symbol headings',()=>{
 const source='## 京都 2026 & 秋\n### 清水寺\n#### 清水寺\n## !!! / <script>bad()</script>\n## 京都 2026 & 秋'
 const a=articleMarkdown(source,'post-123'),b=articleMarkdown(source,'post-123')
 expect(a).toEqual(b);expect(a.headings.map(x=>x.level)).toEqual([2,3,4,2,2]);expect(new Set(a.headings.map(x=>x.id)).size).toBe(5)
 const div=document.createElement('div');div.innerHTML=a.html
 for(const item of a.headings){expect(item.id).toMatch(/^[a-zA-Z0-9_-]+$/);expect(div.querySelector('#'+item.id)?.textContent?.trim()).toBe(item.text)}
 expect(a.html).not.toContain('<script>');expect(a.headings[0]?.text).toContain('京都')
})
it('leaves heading-free content without a directory and does not include H1/H5/code',()=>{
 expect(articleMarkdown('普通正文','body').headings).toEqual([])
 expect(articleMarkdown('# Title\n##### 小标题\n```md\n## code\n```','body').headings).toEqual([])
})
it('keeps original sanitization and prevents forged IDs or reader markers',()=>{
 const result=articleMarkdown('<span id="lj-body-heading-1" data-reading-heading="">伪造</span><a name="lj-body-heading-1"></a>\n\n## 真正标题\n\n<img src="https://bad.invalid/pixel" onerror="bad()"><iframe src="x"></iframe>[坏链接](javascript:bad())','body')
 expect(result.html).not.toMatch(/<img|<iframe|onerror|javascript:/)
 expect(result.html.match(/id="lj-body-heading-1"/g)).toHaveLength(1);expect(result.html.match(/data-reading-heading/g)).toHaveLength(1)
})
it('uses separate stable namespaces for repeated template body modules',()=>{
 expect(articleMarkdown('## 重复','post-1-module-a').headings[0]?.id).not.toBe(articleMarkdown('## 重复','post-1-module-b').headings[0]?.id)
})
it('clamps progress to article bounds and updates when media height changes',()=>{
 expect(readingProgress(0,200,2000,800)).toBe(0);expect(readingProgress(800,200,2000,800)).toBe(50);expect(readingProgress(1400,200,2000,800)).toBe(100);expect(readingProgress(9000,200,2000,800)).toBe(100)
 expect(readingProgress(800,200,3200,800)).toBe(25);expect(readingProgress(0,900,100,800)).toBe(0);expect(readingProgress(200,200,100,800)).toBe(100);expect(readingProgress(300,200,100,800)).toBe(100)
})
it('selects the current chapter through rapid scroll without scanning all headings',()=>{
 expect(currentHeading([100,500,800],0,800)).toBe(0);expect(currentHeading([100,500,800],420,800)).toBe(1);expect(currentHeading([100,500,800],5000,800)).toBe(2)
})
let dispose=()=>{}
afterEach(()=>{dispose();dispose=()=>{};vi.restoreAllMocks();vi.unstubAllGlobals()})
it('tracks an embedded root, supports mobile TOC, instant keyboard targets, resize and cleanup',async()=>{
 let resize!:()=>void,frame!:FrameRequestCallback,articleHeight=2000
 const disconnect=vi.fn(),cancel=vi.fn(),root=document.createElement('div');root.className='editor-preview-scroll';document.body.append(root)
 Object.defineProperty(root,'clientHeight',{value:600});root.scrollTo=vi.fn(({top})=>{root.scrollTop=Number(top)})
 vi.stubGlobal('ResizeObserver',class{constructor(fn:()=>void){resize=fn}observe(){}disconnect=disconnect})
 vi.stubGlobal('requestAnimationFrame',(fn:FrameRequestCallback)=>{frame=fn;return 1});vi.stubGlobal('cancelAnimationFrame',cancel)
 const remove=vi.spyOn(root,'removeEventListener')
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){return {top:this===root?0:this.matches('[data-reading-heading]')?(this.textContent==='二'?1000:300)-root.scrollTop:200-root.scrollTop,height:this.classList.contains('reading-article')?articleHeight:100,width:390} as DOMRect})
 const app=createApp({render:()=>h(ArticleReader,{embedded:true},{default:()=>h(ArticleBody,{source:'## 一\n正文\n### 二\n正文',namespace:'test'})})});app.mount(root);dispose=()=>{app.unmount();root.remove()};await nextTick();await nextTick();await nextTick();frame(0)
 const details=root.querySelector('details')!;expect(details.open).toBe(false);details.open=true;expect(root.querySelector('nav[aria-label="本文目录"]')).not.toBeNull()
 const links=root.querySelectorAll<HTMLAnchorElement>('.reading-toc a');links[1]!.click();expect(root.scrollTo).toHaveBeenCalledWith({top:920,behavior:'auto'});expect(details.open).toBe(false);expect(document.activeElement?.textContent).toBe('二');frame(0);await nextTick();expect(links[1]?.getAttribute('aria-current')).toBe('location')
 root.scrollTop=1600;root.dispatchEvent(new Event('scroll'));frame(0);await nextTick();expect(root.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')).toBe('100')
 articleHeight=3400;resize();frame(0);await nextTick();expect(Number(root.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow'))).toBe(50)
 app.unmount();dispose=()=>root.remove();expect(disconnect).toHaveBeenCalled();expect(cancel).toHaveBeenCalled();expect(remove.mock.calls.map(x=>x[0])).toContain('scroll')
})
it('renders accessible text-only neighboring cards without loading absent media',()=>{
 const root=document.createElement('div');document.body.append(root);const app=createApp({render:()=>h(AdjacentPosts,{data:{previous:null,next:{id:'n',title:'没有封面的故事',display_date:'2026-10-20',cover:null}}})});app.mount(root);dispose=()=>{app.unmount();root.remove()}
 expect(root.querySelector('img')).toBeNull();expect(root.querySelector('a')?.getAttribute('href')).toBe('/posts/n');expect(root.textContent).toContain('下一篇');expect(root.textContent).toContain('全站已发布')
})

it('preserves safe pre-existing authored anchors as aliases without replacing unique TOC IDs',()=>{const result=articleMarkdown('<h2 id="memory">旧章节</h2>','post-1');const root=document.createElement('div');root.innerHTML=result.html;expect(root.querySelector('#memory')?.className).toBe('legacy-heading-anchor');expect(root.querySelector('h2')?.id).toBe(result.headings[0]?.id);expect(root.querySelectorAll('[id]')).toHaveLength(2)})

it('tracks closed nested modules at the visible summary without zero-offset chapter jumps',async()=>{
 const {visibleReadingTarget}=await import('./tracking')
 const boundary=document.createElement('article'),outer=document.createElement('details'),inner=document.createElement('details'),heading=document.createElement('h2')
 boundary.append(outer);outer.append(inner);inner.append(heading)
 expect(visibleReadingTarget(heading,boundary)).toBe(outer)
 outer.open=true;expect(visibleReadingTarget(heading,boundary)).toBe(inner)
 inner.open=true;expect(visibleReadingTarget(heading,boundary)).toBe(heading)
})
