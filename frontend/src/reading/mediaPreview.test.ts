// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest'
import {createApp,nextTick,type App} from 'vue'
import ArticleBody from './ArticleBody.vue'
import {serializeMedia} from '../writing/body'
import {previewImage} from './mediaPreview'
vi.mock('../presentation/typography',async importOriginal=>({...await importOriginal<typeof import('../presentation/typography')>(),loadTypography:vi.fn(async()=>{})}))
const id='11111111-1111-4111-8111-111111111111',job='22222222-2222-4222-8222-222222222222'
let app:App|undefined,root:HTMLElement|undefined
afterEach(()=>{app?.unmount();root?.remove()})
it('only accepts exact authenticated same-origin preview routes',()=>{const valid='/api/admin/exchange/jobs/'+job+'/images/'+id;expect(previewImage([{id,url:valid}],id)?.url).toBe(valid);for(const url of ['https://tracking.example/photo','//tracking.example/photo','data:image/svg+xml,x','/api/library-media/'+id+'/original',valid+'?redirect=other',valid+'/../other','/api/library-media/'+job+'/preview'])expect(previewImage([{id,url}],id)).toBeUndefined()})
it('renders staged pictures inline using the normal body parser without raw marker text or original downloads',async()=>{root=document.createElement('div');document.body.append(root);const url='/api/admin/exchange/jobs/'+job+'/images/'+id;app=createApp(ArticleBody,{source:'## 开始\n\n'+serializeMedia({id,alt:'合成照片',caption:'记录级说明',widthPercent:60,align:'right',width:960,layout:'auto'}),format:2,namespace:'preview',previewMedia:[{id,url,width:120,height:80}]});app.mount(root);await nextTick();expect(root.querySelector('h2')?.textContent).toBe('开始');expect(root.querySelector('img')?.getAttribute('src')).toBe(url);expect(root.querySelector('figure')?.getAttribute('style')).toContain('60%');expect(root.textContent).toContain('记录级说明');expect(root.textContent).not.toContain(':::lj-media-v1');expect(root.querySelector('.body-photo-button')?.tagName).toBe('DIV');expect(root.textContent).not.toContain('下载原图')})
it('does not fall back to a guessed library route when a preview image is not authorized',async()=>{root=document.createElement('div');document.body.append(root);app=createApp(ArticleBody,{source:serializeMedia({id,alt:'未授权',caption:'',width:960,align:'center',layout:'auto'}),format:2,namespace:'preview',previewMedia:[]});app.mount(root);await nextTick();expect(root.querySelector('img')).toBeNull();expect(root.textContent).toContain('图片暂不可用')})
