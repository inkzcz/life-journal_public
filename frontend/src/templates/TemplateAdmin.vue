<script setup lang="ts">
import {confirmAction,promptAction} from '../ui/confirm'
import {systemDark} from '../ui/theme'
import {newId} from '../ids'
import { computed,ref,onMounted,onUnmounted,watch } from 'vue'
import { onBeforeRouteLeave,useRouter } from 'vue-router'
import { request } from '../api'
import FieldEditor from '../admin/FieldEditor.vue'
import ValueInput from '../admin/ValueInput.vue'
import TemplateRenderer from '../blog/TemplateRenderer.vue'
import { fieldPayload,clone,initialValues } from '../admin/types'
import {styles,palettes,type Appearance,type Style,type PaletteName} from '../blog/types'
import {appearanceAttrs} from '../blog/colors'
import { moduleKinds,fromServer,type TemplateDraft,type DisplayModule } from './types'
const router=useRouter(),items=ref<any[]>([]),presets=ref<any[]>([]),draft=ref<TemplateDraft|null>(null),saved=ref(''),busy=ref(false),error=ref(''),notice=ref('')
const style=ref<Style>('modern-soft'),palette=ref<PaletteName>('celadon'),mode=ref<'light'|'dark'|'system'>('light'),sampleTitle=ref('留住值得记住的片刻'),sampleBody=ref('## 故事从这里开始\n这是未保存的虚构预览。'),values=ref<Record<string,unknown>>({})
const dirty=computed(()=>!!draft.value&&JSON.stringify(draft.value)!==saved.value)
const appearance=computed<Appearance>(()=>({theme:'celadon',style:style.value,palette:palette.value,mode:mode.value}))
const dark=computed(()=>mode.value==='dark'||mode.value==='system'&&systemDark.value)
async function leave(){return !busy.value&&(!dirty.value||await confirmAction('模板尚未保存，确定放弃这些修改吗？'))}
onBeforeRouteLeave(async()=>await leave());function unload(e:BeforeUnloadEvent){if(dirty.value){e.preventDefault();e.returnValue=''}}
async function run(fn:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';notice.value='';try{await fn()}catch(e){error.value=String(e)}finally{busy.value=false}}
async function load(){items.value=await request('/admin/templates');presets.value=await request('/admin/templates/presets')}
function select(t:any){draft.value=fromServer(clone(t));ensureKeys();saved.value=JSON.stringify(draft.value);values.value=initialValues(draft.value.fields.map(f=>({...f,id:f.key})));}
function ensureKeys(){for(const f of draft.value?.fields||[]){if(!f.key)f.key=f.id||newId();if(!f.group)f.group='基本信息'}
 const keys=new Set(draft.value?.fields.map(f=>f.key));for(const m of draft.value?.modules||[])m.field_ids=m.field_ids.filter(id=>keys.has(id))
}
watch(()=>draft.value?.fields,ensureKeys,{deep:true})
async function create(preset?:any){if(!await leave())return;if(preset)select(preset);else select({slug:'',name:'',description:'',active:true,fields:[],modules:['header','body','fields','gallery','related'].map(kind=>({id:newId(),kind,title:'',enabled:true,layout:'grid',field_ids:[]}))});saved.value='';}
async function open(id:string){if(await leave())void run(async()=>select(await request('/admin/templates/'+id)))}
function payload(){if(!draft.value)return;const d=draft.value;const fields=fieldPayload(d.fields).map((f,i)=>{const {key,group,...field}=f as any;return {key:d.fields[i]!.key,group:d.fields[i]!.group,field}});return {slug:d.slug,name:d.name,description:d.description,active:d.active,expected_type_revision:d.expected_type_revision,fields,modules:d.modules,...(d.id?{expected_revision:d.revision}:{})}}
async function save(){void run(async()=>{const d=draft.value!;select(await request('/admin/templates'+(d.id?'/'+d.id:''),{method:d.id?'PUT':'POST',body:JSON.stringify(payload())}));await load();notice.value='模板已保存；已有记录继续使用保存时的版本。'})}
async function cancel(){if(await leave()){if(draft.value?.id)void run(async()=>select(await request('/admin/templates/'+draft.value!.id)));else draft.value=null}}
async function defaults(){if(!draft.value||!await confirmAction('恢复首次保存时的字段与布局，后加字段会停用并保留身份和历史值。尚需保存才生效。继续吗？'))return;if(draft.value.id)void run(async()=>{const t=await request('/admin/templates/'+draft.value!.id+'/defaults');const old=saved.value;select(t);saved.value=old;notice.value='已恢复初始配置预览，尚未保存。'});else notice.value='尚未保存的模板可取消，再重新选择初始模板。'}
async function duplicate(){const d=draft.value;if(!d?.id||!await leave())return;const name=await promptAction('副本名称',d.name+'（副本）');if(!name)return;const slug=await promptAction('副本稳定标识（英文）',d.slug+'-'+newId().slice(0,8));if(!slug)return;void run(async()=>{select(await request('/admin/templates/'+d.id+'/copy',{method:'POST',body:JSON.stringify({name,slug,expected_revision:d.revision})}));await load();notice.value='已创建独立副本，字段身份重新生成；不会复制记录或媒体文件。'})}
function move(i:number,delta:number){const modules=draft.value!.modules;const item=modules.splice(i,1)[0]!;modules.splice(i+delta,0,item)}
function addModule(){draft.value!.modules.push({id:newId(),kind:'fields',title:'信息卡',enabled:true,layout:'grid',field_ids:[]})}
function removeField(f:any){if(f.required){error.value='请先取消必填，再移除可选字段。';return}f.active=false;notice.value='字段已从新表单停用，历史值与旧版本保留。'}
const previewArticle=computed(()=>{const d=draft.value;return {title:sampleTitle.value,body:sampleBody.value,type_name:d?.name||'我的模板',display_date:'2026-10-18',fields:(d?.fields||[]).map(f=>({...f,id:f.key})),values:values.value,media:[],cover:null,links:[],places:[]}})
onMounted(()=>{window.addEventListener('beforeunload',unload);void run(load)});onUnmounted(()=>{window.removeEventListener('beforeunload',unload)})
</script>
<template><main class="container admin-content template-admin"><header><div><span class="eyebrow">CONTENT TEMPLATE STUDIO</span><h1>内容模板</h1><p>一次定义录入方式与阅读布局，留住每个旧版本。</p></div><button class="quiet" :disabled="busy" @click="router.push('/admin/content')">返回内容后台</button></header>
<p v-if="error" class="error" role="alert">{{error}}（输入保留）</p><p v-if="notice" class="notice" role="status">{{notice}}</p>
<section class="card"><h2>选择起点</h2><div class="actions"><button :disabled="busy" @click="create()">创建空白模板</button><button v-for="p in presets" :key="p.key" class="quiet" :disabled="busy" @click="create(p)">使用{{p.name}}</button></div><p class="muted">四种起始配置都可自由编辑，不会自动创建栏目或改动主题。照片、封面、地点和关联记录在内容编辑器中选择。</p><div class="actions"><button v-for="t in items" :key="t.id" class="quiet" :disabled="busy" @click="open(t.id)">{{t.name}} · {{t.active?'启用':'停用'}} · v{{t.revision}}</button></div></section>
<template v-if="draft"><form class="card template-form" @submit.prevent="save"><fieldset :disabled="busy"><h2>{{draft.id?'编辑模板':'新建模板'}}</h2><div class="editor-meta"><label>模板名称<input v-model="draft.name" required maxlength="100" /></label><label>模板稳定标识<input v-model="draft.slug" :disabled="!!draft.id" required pattern="[a-z][a-z0-9_-]{0,79}" maxlength="80" /></label></div><label>模板说明<textarea v-model="draft.description" maxlength="2000" rows="2" /></label><label class="checks"><input v-model="draft.active" type="checkbox" /> 启用模板（停用后已有记录仍可阅读）</label>
<FieldEditor :fields="draft.fields" :disabled="busy"><template #extra="{field}"><label>表单分组<input v-model="field.group" maxlength="100" /></label><button v-if="field.id&&field.active" type="button" class="quiet" @click="removeField(field)">从模板移除可选字段（保留历史）</button></template></FieldEditor>
<h3>前台展示模块</h3><p class="muted">绑定字段后，前台按这里的顺序显示。未展示的已保存值仍可从“其他已保存字段”展开阅读。时间线只绑定日期字段。</p>
<section v-for="(m,i) in draft.modules" :key="m.id" class="field-config module-config"><div class="actions"><strong>模块 {{i+1}}</strong><button type="button" class="quiet" :disabled="i===0" @click="move(i,-1)">模块上移</button><button type="button" class="quiet" :disabled="i===draft.modules.length-1" @click="move(i,1)">模块下移</button><button type="button" class="quiet" @click="draft.modules.splice(i,1)">移除模块</button></div><div class="editor-meta"><label>模块种类<select aria-label="模块种类" v-model="m.kind" @change="m.field_ids=[]"><option v-for="(name,key) in moduleKinds" :key="key" :value="key">{{name}}</option></select></label><label>模块标题<input v-model="m.title" maxlength="100" /></label></div><label class="checks"><input v-model="m.enabled" type="checkbox" /> 显示模块</label><label v-if="['gallery','album'].includes(m.kind)">画廊布局<select aria-label="画廊布局" v-model="m.layout"><option value="grid">网格</option><option value="masonry">瀑布流</option><option value="large">大图画廊</option></select></label><label v-if="['gallery','album'].includes(m.kind)">照片分组方式<select aria-label="照片分组方式" v-model="m.group_by"><option value="none">不分组</option><option value="manual">手工分组</option><option value="date">按照片日期</option><option value="place">按照片地点</option></select></label><label v-if="m.kind==='fields'">信息卡布局<select aria-label="信息卡布局" v-model="m.layout"><option value="card">信息卡</option><option value="grid">摘要网格</option><option value="date">日期主题</option></select></label><div v-if="['summary','fields','timeline'].includes(m.kind)" class="checks"><label v-for="f in draft.fields.filter(f=>m.kind!=='timeline'||f.kind==='date')" :key="f.key"><input v-model="m.field_ids" type="checkbox" :value="f.key" />{{f.name||'未命名字段'}}</label></div></section>
<button type="button" class="quiet" :disabled="draft.modules.length>=20" @click="addModule">添加展示模块</button>
<div class="actions admin-save"><button type="submit">保存模板</button><button type="button" class="quiet" @click="cancel">取消模板修改</button><button type="button" class="quiet" @click="defaults">恢复默认（待保存）</button><button v-if="draft.id" type="button" class="quiet" @click="duplicate">复制模板</button><span v-if="dirty" class="muted">有未保存的配置</span></div></fieldset></form>
<section class="card"><h2>实时预览 · 未保存</h2><p class="muted">预览使用虚构输入；实际照片、封面和关联内容在记录编辑器中选择，可使用记录的前台预览。</p><div class="editor-meta"><label>预览风格<select v-model="style" aria-label="预览风格"><option v-for="(name,key) in styles" :key="key" :value="key">{{name}}</option></select></label><label>预览配色<select v-model="palette" aria-label="预览配色"><option v-for="(name,key) in palettes" :key="key" :value="key">{{name}}</option></select></label><label>预览模式<select v-model="mode" aria-label="预览模式"><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label></div><details><summary>编辑虚构预览内容</summary><label>预览标题<input v-model="sampleTitle" /></label><label>预览正文<textarea v-model="sampleBody" rows="4" /></label><ValueInput v-for="f in draft.fields.filter(f=>f.active)" :key="f.key" :field="f" v-model="values[f.key!]" :label="'预览 '+f.name" /></details><div class="blog lj-theme template-live-preview" v-bind="appearanceAttrs(appearance)" :data-mode="dark?'dark':'light'"><TemplateRenderer :article="previewArticle" :config="draft" /></div></section>
</template></main></template>
<style scoped>
.template-form{margin:24px 0}.template-admin header{flex-wrap:wrap}.template-live-preview{margin-top:24px;padding:24px;min-height:300px;border-radius:var(--ui-radius)}.template-admin{max-width:1250px}.template-admin details>summary{min-height:44px;padding:12px;cursor:pointer}.module-config{border-left:3px solid var(--ui-line)}.template-admin input[type=checkbox]{width:auto}.template-admin h1{overflow-wrap:anywhere}
@media(max-width:760px){.template-live-preview{padding:16px}.template-admin header button{width:100%}}
</style>
