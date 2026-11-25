<script setup lang="ts">
import {newId} from '../ids'
import {entryTransferKey} from '../writing/entryTransfer'
import type {Entry} from '../writing/entries'
import EntryTargetPicker from '../writing/EntryTargetPicker.vue'
import {confirmAction} from '../ui/confirm'
import ThemeOrnament from '../blog/ThemeOrnament.vue'
import { ref, computed, onMounted, onUnmounted, nextTick, watch, inject, provide, defineAsyncComponent } from 'vue'
const BodyEditor=defineAsyncComponent(()=>import('../writing/BodyEditor.vue'))
const WritingAssistant=defineAsyncComponent(()=>import('../exchange/WritingAssistant.vue'))
import type {AIEditor} from '../exchange/selection'
import ModuleHeading from '../writing/ModuleHeading.vue'
import ModuleIcon from '../writing/ModuleIcon.vue'
import TypographyPanel from '../presentation/TypographyPanel.vue'
import {travelFields} from '../writing/travelDates'
import EditorResources from '../writing/EditorResources.vue'
import {serializeMedia,bodyParts,bodyMedia} from '../writing/body'
import ArticleBody from '../reading/ArticleBody.vue'
import { request } from '../api'
import { onBeforeRouteLeave, routerKey } from 'vue-router'
import { createSaveSession } from './saveSession'
import TagPicker from '../discovery/TagPicker.vue'
import RecordPreview from './RecordPreview.vue'
import { renderMarkdown } from '../markdown'
import LifeEditor from '../life/LifeEditor.vue'
import { emptyLife,lifePayload,type Life } from '../life/types'
import { formGroups } from '../templates/types'
import FieldEditor from './FieldEditor.vue'
import ValueInput from './ValueInput.vue'
import ResourceManager from './ResourceManager.vue'
import ConnectionsEditor from './ConnectionsEditor.vue'
import ConnectionsView from './ConnectionsView.vue'
import { emptyConnections, connectionsPayload, type Connections } from './archive'
import { clone, fieldPayload, initialValues, type Field, type ContentType, type TypeSummary, type ContentRecord, type RecordSummary } from './types'

type TypeDraft={id?:string;slug:string;name:string;description:string;active:boolean;revision:number;fields:Field[]}
type RecordDraft={marker_version?:1|2;article?:{end_date:string|null;travel_enabled:boolean};is_food?:boolean;itinerary_generation?:{status:string;message?:string};media_folder_id?:string;new_media_ids?:string[];marked_places?:{place_id:string}[];summary?:string;body_format?:number;tags?:{id:string;name:string}[];life?:Life;template?:any;id?:string;type_id:string;schema_version:number;current_type_version:number;type_active:boolean;title:string;body:string;display_date:string;status:'draft'|'published';values:Record<string,unknown>;revision:number;fields:Field[];connections:Connections}
const props=defineProps<{immersive?:boolean;previewOnly?:boolean;recordId?:string;initialTemplateId?:string;publishIntent?:boolean}>()
const workspace=ref('body'),toolsOpen=ref(true)
const workspaceModules=computed(()=>[{id:'basic',name:'基本信息'},{id:'body',name:'正文编辑'},{id:'media',name:'图片与资源'},...(isTravel.value?[{id:'itinerary',name:'行程管理'}]:[]),{id:'relations',name:'关联内容'},{id:'publish',name:'发布设置'}])
const itineraryPending=ref(false),schemaUpgradePending=ref(false)
const uploadsPending=ref(false),placePending=ref(false),bodyEditorKey=ref(0)
const bodyEditor=ref<AIEditor|null>(null),assistantOpen=ref(false)
const emit=defineEmits<{(event:'exit'):void}>()
const section=ref<'types'|'records'|'media'|'places'>('types'), types=ref<TypeSummary[]>([]), records=ref<RecordSummary[]>([])
const templates=ref<any[]>([]),creationMode=ref<'daily'|'travel'>('daily')
const tripFields=computed(()=>travelFields(record.value?.fields||[]))
const isTravel=computed(()=>record.value?.article?.travel_enabled??false)
function setRecordingMode(mode:'daily'|'travel'){const d=record.value;if(d)d.article={...(d.article||{end_date:null}),travel_enabled:mode==='travel'}}
const dateConflicts=computed(()=>{const d=record.value;if(!d?.life||!isTravel.value)return [];return (['start','end'] as const).filter(k=>{const f=tripFields.value[k],v=f&&d.values[f.id!],actual=d.life![k==='start'?'start_date':'end_date'];return !!v&&!!actual&&v!==actual})})
function tripDate(k:'start'|'end',v:string){const d=record.value;if(!d?.life)return;d.life[k==='start'?'start_date':'end_date']=v||null;const f=tripFields.value[k];if(f)d.values[f.id!]=v||null}
function resolveDates(source:'fields'|'life'){const d=record.value;if(!d?.life)return;for(const k of ['start','end'] as const){const f=tripFields.value[k];tripDate(k,String((source==='fields'&&f?d.values[f.id!]:d.life[k==='start'?'start_date':'end_date'])||''))}}
const foodFields=computed(()=>record.value?.fields.filter(f=>f.purpose&&f.active)||[])
const isFood=computed(()=>record.value?.is_food||foodFields.value.length>0)
const groupedFields=computed(()=>{const d=record.value,trip=tripFields.value;const special=isTravel.value?[trip.start?.id,trip.end?.id,trip.companions?.id,...trip.lodging.map(f=>f.id)]:[];return formGroups((d?.fields||[]).filter(f=>!special.includes(f.id)&&(!f.purpose||!f.active)),d?.template?.config)})
const typeDraft=ref<TypeDraft|null>(null), record=ref<RecordDraft|null>(null)
const busy=ref(false),error=ref(''),notice=ref(''),chosenType=ref(''),filterStatus=ref(new URLSearchParams(window.location.search).get('status')==='draft'?'draft':''),filterType=ref(''),page=ref(1),total=ref(0),bodyPreview=ref(false),recordMode=ref<'view'|'edit'>('view')
const resourceManager=ref<{canLeave:()=>boolean|Promise<boolean>}|null>(null)
const saved=ref('');let alive=true
const serverStatus=ref<'draft'|'published'>('draft'),previewRecord=ref<{id:string;revision:number;status:string}|null>(null)
function recordPayload(d:RecordDraft){return {marker_version:d.marker_version??2,...(d.article?{article:{...d.article,end_date:d.article.end_date||null}}:{}),new_media_ids:d.new_media_ids||[],summary:d.summary||'',tag_ids:(d.tags||[]).map(t=>t.id),life:lifePayload(d.life||emptyLife()),...(d.template?{template:{id:d.template.id,version:d.template.version}}:{}),connections:connectionsPayload(d.connections),title:d.title,body:d.body,body_format:d.body_format||1,display_date:d.display_date,status:d.status,schema_version:d.schema_version,values:d.values}}
function recordSnapshot(){return record.value?JSON.stringify(recordPayload(record.value)):''}
function toDraft(result:ContentRecord):RecordDraft{return {...clone(result),life:clone((result as ContentRecord & {life?:Life}).life||emptyLife()),connections:clone((result as ContentRecord & {connections?:Connections}).connections||emptyConnections())}}
const editor=createSaveSession<ContentRecord>({
 snapshot:recordSnapshot,enabled:()=>!props.previewOnly&&section.value==='records'&&recordMode.value==='edit'&&!!record.value,identity:()=>record.value?.id,
 blocked:()=>schemaUpgradePending.value?'餐厅字段已加载，请手动保存以升级当前记录。':dateConflicts.value.length?'旅行日期来源存在冲突，请明确选择后保存。':placePending.value?'请先保存或取消同页地点编辑。':uploadsPending.value?'请先确认输入法文字并完成或取消图片上传，再保存文章。':!record.value?.id?'新记录请先手动创建草稿。':serverStatus.value==='published'?'已发布记录不自动保存；手动保存将更新读者可见内容。':record.value.status!=='draft'?'发布必须手动保存确认，不会自动发布。':'',
 persist:async(snapshot,revision,signal)=>{const d=record.value!;return await request('/admin/content/records'+(d.id?'/'+d.id:''),{method:d.id?'PUT':'POST',signal,body:JSON.stringify({...JSON.parse(snapshot),...(d.id?{expected_revision:revision}:{type_id:d.type_id})})}) as ContentRecord},
 accept:(result,sent)=>{schemaUpgradePending.value=false;const confirmed=toDraft(result),unchanged=recordSnapshot()===sent;serverStatus.value=confirmed.status;if(unchanged)record.value=confirmed;else if(record.value){record.value.id=confirmed.id;record.value.media_folder_id=confirmed.media_folder_id;const sentMedia=JSON.parse(sent).new_media_ids||[];record.value.new_media_ids=(record.value.new_media_ids||[]).filter(id=>!sentMedia.includes(id));record.value.revision=confirmed.revision;record.value.current_type_version=confirmed.current_type_version}return {snapshot:JSON.stringify(recordPayload(confirmed)),revision:confirmed.revision}}
})
const dateFields=computed(()=>record.value?.fields.filter(f=>f.kind==='date'&&typeof record.value?.values[f.id||'']==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(String(record.value.values[f.id||'']))).map(f=>({id:f.id!,name:f.name,value:String(record.value!.values[f.id!])}))||[])
const lifeConnections=computed(()=>{const d=record.value;if(!d)return emptyConnections();const media=[...d.connections.media];for(const m of bodyMedia(d.body,d.body_format||1)){if(!media.some(item=>item.id===m.id)){media.push({id:m.id,cover:false,caption:m.caption,asset:{id:m.id,filename:m.alt||'正文图片',alt:m.alt,title:m.alt,description:'',width:m.width,height:0,size:0,mime_type:'image/webp',revision:1,created_at:''}})}}return {...d.connections,media}})
const saveState=editor.state
const saveLabels={unchanged:'未修改',dirty:'有未保存更改',waiting:'等待自动保存',saving:'正在保存',saved:'已保存',error:'保存失败',conflict:'发生编辑冲突',blocked:'当前内容不能自动保存'}
function beginEditing(){if(record.value){serverStatus.value=record.value.status;editor.begin(recordSnapshot(),record.value.revision)}}
watch([recordSnapshot,()=>recordMode.value,()=>section.value,uploadsPending,placePending],()=>editor.changed())
watch(()=>record.value?.id,id=>{if(!props.previewOnly&&props.immersive&&id&&routeRouter&&routeRouter.currentRoute.value.path!==('/write/'+id))void routeRouter.replace('/write/'+id)})
watch(()=>props.recordId,id=>{if(props.immersive&&id&&id!==record.value?.id)openRecord(id)})
const pages=computed(()=>Math.max(1,Math.ceil(total.value/20)))
const snapshot=()=>JSON.stringify(section.value==='types'?typeDraft.value:record.value)
const dirty=computed(()=>section.value==='types'?!!typeDraft.value&&snapshot()!==saved.value:!!record.value&&recordMode.value==='edit'&&editor.dirty())
const entryTransfer=ref<{entry:Entry;operation:'copy'|'move';requestId:string;sourceId:string}|null>(null),transferError=ref('')
provide(entryTransferKey,async(entry,operation)=>{
 if(props.previewOnly||!record.value||busy.value||saveState.saving)return
 if(uploadsPending.value||placePending.value||itineraryPending.value){error.value='请先完成当前媒体、地点或行程编辑';return}
 if(!record.value.id||editor.dirty()){
  if(!await confirmAction('跨文章操作前需要先保存当前文章，保存成功后继续。'))return
  await saveRecord()
  if(!record.value?.id||editor.dirty()){error.value='当前文章未确认保存，已取消卡片操作';return}
 }
 entryTransfer.value={entry:clone(entry),operation,requestId:newId(),sourceId:record.value.id};transferError.value=''
})
async function transferEntry(target:{id:string;revision:number;title:string}){
 const action=entryTransfer.value,d=record.value
 if(!action||!d?.id||busy.value||saveState.saving)return
 if(editor.dirty()){transferError.value='当前文章发生未保存修改，请取消并先保存';return}
 busy.value=true;transferError.value=''
 try{
  await request('/admin/content/records/'+d.id+'/entry-operation',{method:'POST',body:JSON.stringify({operation:action.operation,target_id:target.id,entry_id:action.entry.id,request_id:action.requestId,source_revision:d.revision,target_revision:target.revision})})
  const fresh=await request('/admin/content/records/'+d.id) as ContentRecord
  if(alive){record.value=toDraft(fresh);beginEditing();bodyEditorKey.value++;saved.value=snapshot();entryTransfer.value=null;notice.value='卡片操作成功，文章版本已同步'}
 }catch(e){if(alive)transferError.value='操作未确认完成，请保留当前选择重试；冲突时取消并重新读取文章。'+String(e)}finally{if(alive)busy.value=false}
}

async function canLeave(){return (!resourceManager.value||await resourceManager.value.canLeave())&&!busy.value&&(!placePending.value||await confirmAction('有尚未保存的地点编辑，确定放弃吗？'))&&(!uploadsPending.value||await confirmAction('有尚未完成或失败的上传，离开后需重新选择文件。确定离开吗？'))&&(!dirty.value||await confirmAction('有尚未确认保存的修改，确定放弃本页输入吗？在途请求可能已经写入，请返回后核对服务器版本。'))}
const routeRouter=inject(routerKey,undefined)
if(routeRouter&&!props.previewOnly)onBeforeRouteLeave(async to=>props.immersive&&record.value?.id&&to.path==='/write/'+record.value.id||await canLeave())
function retainExpired(event:Event){if(dirty.value||saveState.saving||uploadsPending.value||placePending.value||itineraryPending.value)event.preventDefault()}
defineExpose({canLeave})
async function run(action:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';notice.value='';try{await action()}catch(e){if(alive)error.value=String(e)}finally{if(alive){busy.value=false;if(error.value){await nextTick();const f=record.value?.fields.find(f=>error.value.includes(f.name));const target=f?document.querySelector<HTMLElement>('[data-field-id="'+f.id+'"] input,[data-field-id="'+f.id+'"] textarea,[data-field-id="'+f.id+'"] select'):document.querySelector<HTMLElement>('.admin-content [role=alert]');target?.scrollIntoView?.({block:'center'});target?.focus?.()}}}}
async function loadTypes(){const result=await request('/admin/content/types') as TypeSummary[];if(alive){types.value=result;if(!chosenType.value)chosenType.value=result.find(t=>t.active)?.id||''}}
async function loadRecords(){templates.value=await request('/admin/templates');
  const available=types.value.filter(t=>t.active&&!templates.value.some(x=>x.type_id===t.id));if(!available.some(t=>t.id===chosenType.value))chosenType.value=available[0]?.id||''
  const params=new URLSearchParams({page:String(page.value),page_size:'20'});if(filterStatus.value)params.set('status',filterStatus.value);if(filterType.value)params.set('type_id',filterType.value);const result=await request('/admin/content/records?'+params) as {items:RecordSummary[];total:number};if(alive){total.value=result.total;if(page.value>pages.value){page.value=pages.value;await loadRecords();return}records.value=result.items}}
function clear(){assistantOpen.value=false;schemaUpgradePending.value=false;workspace.value='basic';bodyEditorKey.value++;uploadsPending.value=false;placePending.value=false;editor.begin('',0);previewRecord.value=null;typeDraft.value=null;record.value=null;saved.value='';error.value='';notice.value='';bodyPreview.value=false}
async function tab(value:'types'|'records'|'media'|'places'){if(value===section.value||!await canLeave())return;clear();section.value=value;if(value==='records')void run(loadRecords)}
async function newType(){if(!await canLeave())return;clear();section.value='types';typeDraft.value={slug:'',name:'',description:'',active:true,revision:0,fields:[]};saved.value=snapshot()}
async function openType(id:string){if(!await canLeave())return;void run(async()=>{const result=await request('/admin/content/types/'+id) as ContentType;if(alive){section.value='types';typeDraft.value=clone(result);saved.value=snapshot()}})}
async function saveType(){if(!typeDraft.value)return;const draft=typeDraft.value;await run(async()=>{
  const payload={slug:draft.slug,name:draft.name,description:draft.description,active:draft.active,fields:fieldPayload(draft.fields),...(draft.id?{expected_revision:draft.revision}:{})}
  const result=await request('/admin/content/types'+(draft.id?'/'+draft.id:''),{method:draft.id?'PUT':'POST',body:JSON.stringify(payload)}) as ContentType
  if(!alive)return;typeDraft.value=clone(result);saved.value=snapshot();notice.value='内容类型已保存，历史配置和记录均保留';await loadTypes()
})}
async function startRecord(id='',templateId?:string){if(!await canLeave())return;void run(async()=>{
  const selected=templateId?await request('/admin/templates/'+templateId):null
  if(selected)id=selected.type_id
  const template=selected?{id:selected.id,version:selected.version,current_version:selected.version,config:{form:selected.fields.map((f:any)=>({id:f.key,group:f.group})),modules:selected.modules}}:undefined
  const t=(id?await request('/admin/content/types/'+id):await request('/admin/content/types/default-article',{method:'POST'})) as ContentType
  if(!t.active)throw new Error('该类型已停用，不能新建记录')
  if(selected&&selected.schema_version!==t.version)throw new Error('模板字段已在类型管理中变化，请先重新保存模板以确认最新字段。')
  if(!alive)return;clear();section.value='records';recordMode.value='edit';record.value={marker_version:2,article:{end_date:null,travel_enabled:creationMode.value==='travel'},is_food:t.is_food,tags:[],life:emptyLife(),template,connections:emptyConnections(),type_id:t.id,schema_version:t.version,current_type_version:t.revision,type_active:t.active,title:'',body:'',display_date:new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date()),status:'draft',values:initialValues(t.fields),revision:0,fields:clone(t.fields)};saved.value=snapshot();beginEditing()
})}
async function setCover(id:string){if(!record.value)return;await run(async()=>{const asset=await request('/admin/archive/media/'+id);if(!record.value)return;for(const m of record.value.connections.media)m.cover=false;const found=record.value.connections.media.find(m=>m.id===id);if(found)found.cover=true;else record.value.connections.media.push({id,cover:true,caption:'',asset})})}
function removeMediaReference(id:string){const d=record.value;if(!d)return;d.body=bodyParts(d.body,d.body_format||1).filter(p=>p.media?.id!==id).map(p=>p.media?p.raw||serializeMedia(p.media):p.source).join('');d.connections.media=d.connections.media.filter(m=>m.id!==id);if(d.life){d.life.photos=d.life.photos.filter(p=>p.media_id!==id);for(const a of d.life.activities)a.media_ids=a.media_ids.filter(x=>x!==id)}}
async function openRecord(id:string){if(!await canLeave())return;void run(async()=>{const result=await request('/admin/content/records/'+id) as ContentRecord;if(alive){clear();section.value='records';record.value={...clone(result),life:clone((result as ContentRecord & {life?:Life}).life||emptyLife()),connections:clone((result as ContentRecord & {connections?:Connections}).connections||emptyConnections())};recordMode.value=props.immersive?'edit':'view';bodyPreview.value=false;saved.value=snapshot();beginEditing()}})}
function edit(){recordMode.value='edit';saved.value=snapshot();bodyPreview.value=false;beginEditing()}
async function saveRecord(){
 if(props.previewOnly)return
 if(!record.value||busy.value||saveState.saving||uploadsPending.value||placePending.value||itineraryPending.value)return
 if(dateConflicts.value.length){error.value='旅行日期有冲突，请明确选择使用哪个来源。';return}
 if((serverStatus.value==='published'||record.value.status==='published')&&!await confirmAction(record.value.status==='draft'?'将已发布记录撤回草稿，读者将无法再访问。确定保存吗？':'此操作会更新已发布内容或发布当前记录，已登录读者将能看到。确定手动保存吗？'))return
 if(await editor.save('manual')){if(!editor.dirty()&&!uploadsPending.value){recordMode.value=props.immersive?'edit':'view';saved.value=snapshot()}try{await loadRecords()}catch(e){if(alive)error.value='文章已保存，列表刷新失败：'+String(e)}if(alive)notice.value='记录已保存'}
}
async function openPreview(){
 if(!record.value||busy.value||saveState.saving||uploadsPending.value||placePending.value||itineraryPending.value)return
 if(dateConflicts.value.length){error.value='旅行日期有冲突，请明确选择使用哪个来源。';return}
 if(serverStatus.value==='published'&&editor.dirty()){notice.value='已发布记录有未保存修改，请先明确手动保存，再预览；不会为预览而更新已发布内容。';return}
 if(record.value.status!=='draft'&&editor.dirty()){notice.value='预览不会发布，请先将记录状态改为草稿并保存。';return}
 if(!(await editor.save('preview'))||editor.dirty()||!record.value.id)return
 previewRecord.value={id:record.value.id,revision:saveState.revision,status:serverStatus.value}
}
function reloadServer(){if(record.value?.id)openRecord(record.value.id)}
async function enableFoodFields(){const d=record.value;if(!d?.template||dirty.value||!await confirmAction('为该美食模板新增可选餐厅信息字段；历史文章不会被改写，当前文章需手动保存才升级。继续吗？'))return;void run(async()=>{const result=await request('/admin/food/types/'+d.type_id+'/fields',{method:'POST',body:JSON.stringify({expected_type_revision:d.current_type_version,expected_template_revision:d.template.current_version,confirmation:'新增可选餐厅信息字段'})});const t=result.type,template=result.template;schemaUpgradePending.value=true;d.fields=clone(t.fields);d.values=initialValues(t.fields,d.values);d.schema_version=t.version;d.current_type_version=t.revision;d.template={id:template.id,version:template.version,current_version:template.version,config:{form:template.fields.map((f:any)=>({id:f.key,group:f.group})),modules:template.modules}};notice.value='可选字段已加载，原值保留；请手动保存当前文章。'})}
async function upgradeFields(){if(!record.value||!await confirmAction('将采用最新字段及模板配置。原值会保留，发布时需补齐新的必填字段。继续吗？'))return;const draft=record.value;void run(async()=>{
  const t=await request('/admin/content/types/'+draft.type_id) as ContentType
  if(draft.template){const template=await request('/admin/templates/'+draft.template.id);if(template.schema_version!==t.version)throw new Error('请先在模板管理中确认并保存最新字段配置');draft.template={id:template.id,version:template.version,current_version:template.version,config:{form:template.fields.map((f:any)=>({id:f.key,group:f.group})),modules:template.modules}}}
  if(alive){draft.fields=clone(t.fields);draft.values=initialValues(t.fields,draft.values);draft.schema_version=t.version;draft.current_type_version=t.revision;notice.value='已加载最新配置，尚未保存'}
})}
async function removeRecord(){if(!record.value?.id||!await canLeave()||!await confirmAction('将记录移入回收状态，保留原始内容和编辑历史。继续吗？'))return;const draft=record.value;void run(async()=>{await request('/admin/content/records/'+draft.id,{method:'DELETE',body:JSON.stringify({expected_revision:draft.revision})});if(alive){record.value=null;saved.value='';notice.value='记录已软删除，数据保留';await loadRecords()}})}
async function filter(){if(!await canLeave())return;record.value=null;page.value=1;saved.value='';void run(loadRecords)}
async function turnPage(next:number){if(next<1||next>pages.value||!await canLeave())return;record.value=null;saved.value='';page.value=next;void run(loadRecords)}
async function exit(){if(routeRouter||await canLeave())emit('exit')}
async function navigateTo(path:string,event:Event){event.preventDefault();if(routeRouter)void routeRouter.push(path);else if(await canLeave())window.location.assign(path)}
function saveKey(e:KeyboardEvent){if(props.previewOnly){if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s')e.preventDefault();return}if(!record.value||recordMode.value!=='edit'||section.value!=='records'||!(e.ctrlKey||e.metaKey)||e.key.toLowerCase()!=='s')return;e.preventDefault();if(e.repeat||e.isComposing||uploadsPending.value||placePending.value||itineraryPending.value||saveState.saving)return;void saveRecord()}
function publishRecord(){if(props.previewOnly||!record.value||uploadsPending.value||placePending.value||itineraryPending.value||saveState.saving)return;record.value.status='published';void saveRecord()}
function beforeUnload(e:BeforeUnloadEvent){if(dirty.value||uploadsPending.value||placePending.value||itineraryPending.value){e.preventDefault();e.returnValue=''}}
function display(field:Field,value:unknown){if(value===null||value===undefined)return '未填写';if(field.kind==='select'||field.kind==='multiselect'){const values=Array.isArray(value)?value:[value];return values.map(v=>field.rules.options?.find(o=>o.id===v)?.label||String(v)).join('、')}return String(value)}
onMounted(()=>{window.addEventListener('keydown',saveKey);window.addEventListener('session-expired',retainExpired,true);window.addEventListener('beforeunload',beforeUnload);void run(async()=>{await loadTypes();if(props.immersive||filterStatus.value){section.value='records';await loadRecords();if(props.recordId){const result=await request('/admin/content/records/'+props.recordId) as ContentRecord;record.value=toDraft(result);recordMode.value='edit';beginEditing();if(props.publishIntent&&record.value)record.value.status='published'}}}).then(()=>{if(props.initialTemplateId&&!props.recordId)startRecord('',props.initialTemplateId)})})
onUnmounted(()=>{window.removeEventListener('keydown',saveKey);alive=false;editor.stop();window.removeEventListener('session-expired',retainExpired,true);window.removeEventListener('beforeunload',beforeUnload)})
</script>
<template><EntryTargetPicker v-if="entryTransfer" :entry="entryTransfer.entry" :operation="entryTransfer.operation" :source-id="entryTransfer.sourceId" :busy="busy" :error="transferError" @cancel="entryTransfer=null" @confirm="transferEntry"/>
  <section class="admin-content" :class="{'immersive-writing':immersive}">
    <div v-if="!immersive" class="admin-heading"><div><span class="eyebrow">PRIVATE CONTENT STUDIO</span><h2>内容管理</h2><p class="muted">直接记录日常与旅行；高级字段可按需设置。</p></div><button class="quiet" :disabled="busy" @click="exit">返回私人Blog</button></div>
    <nav v-if="!immersive" class="admin-tabs" aria-label="管理区域"><button :class="{quiet:section!=='types'}" :disabled="busy" @click="tab('types')">内容类型</button><button :class="{quiet:section!=='records'}" :disabled="busy" @click="tab('records')">内容记录</button><button :class="{quiet:section!=='media'}" :disabled="busy" @click="tab('media')">媒体库</button><button :class="{quiet:section!=='places'}" :disabled="busy" @click="tab('places')">地点管理</button></nav>
    <p v-if="error" class="error" role="alert" tabindex="-1">{{error}}（未保存的输入会保留。）</p><p v-if="notice&&(!immersive||notice!=='记录已保存')" class="notice" role="status">{{notice}}</p><p v-if="busy" role="status">正在处理…</p>
    <div v-if="section==='types'" class="admin-layout">
      <aside class="card"><div class="asidehead"><h3>我的内容类型</h3><button :disabled="busy" @click="newType">创建类型</button></div><p v-if="!types.length" class="muted">还没有类型，可以自由定义名称和字段。</p>
        <button v-for="t in types" :key="t.id" class="entry" :disabled="busy" @click="openType(t.id)"><strong>{{t.name}}</strong><small>{{t.active?'启用中':'已停用，历史保留'}} · {{t.slug}}</small></button>
      </aside>
      <article class="card admin-editor">
        <form v-if="typeDraft" @submit.prevent="saveType"><fieldset :disabled="busy"><h3>{{typeDraft.id?'编辑内容类型':'创建内容类型'}}</h3>
          <label>类型名称<input v-model="typeDraft.name" required maxlength="100" /></label><label>稳定标识<input v-model="typeDraft.slug" required :disabled="!!typeDraft.id" maxlength="80" pattern="[a-z][a-z0-9_-]{0,79}" placeholder="英文开头，可用小写字母、数字、横线" /></label>
          <label>类型说明<textarea v-model="typeDraft.description" maxlength="2000" rows="2" /></label><label class="checks"><input v-model="typeDraft.active" type="checkbox" /> 启用类型（停用不会删除记录）</label>
          <FieldEditor :fields="typeDraft.fields" :disabled="busy" />
          <div class="actions admin-save"><button type="submit">保存类型配置</button><button v-if="typeDraft.id" type="button" class="quiet" @click="openType(typeDraft.id)">重新读取类型配置</button><span v-if="dirty" class="muted">有未保存的配置</span></div>
        </fieldset></form><p v-else class="muted">选择一个类型进行编辑，或创建全新的类型。这里不会预置固定栏目。</p>
      </article>
    </div>
    <ResourceManager v-else-if="section==='media'||section==='places'" :key="section" ref="resourceManager" :mode="section" @record="openRecord" />
    <template v-else>
      <section v-if="!immersive||!record" class="card record-tools new-record" aria-label="新建记录">
        <fieldset class="record-mode" :disabled="busy"><legend>选择记录模式</legend>
          <label><input v-model="creationMode" type="radio" value="daily" name="new-record-mode"/>日常记录</label>
          <label><input v-model="creationMode" type="radio" value="travel" name="new-record-mode"/>旅行记录</label>
        </fieldset>
        <button :disabled="busy" @click="startRecord()">新建记录</button>
        <details class="advanced-record-type"><summary>高级内容类型（可选）</summary>
          <label>高级内容类型<select aria-label="高级内容类型" v-model="chosenType" :disabled="busy"><option value="">请选择启用的类型</option><option v-for="t in types.filter(t=>t.active&&!templates.some(x=>x.type_id===t.id))" :key="t.id" :value="t.id">{{t.name}}</option></select></label>
          <button type="button" class="quiet" :disabled="busy||!chosenType" @click="startRecord(chosenType)">使用高级类型新建</button>
        </details>
      </section>
      <div class="admin-layout">
        <aside v-if="!immersive" class="card"><h3>内容记录</h3><label>发布状态<select aria-label="按发布状态筛选" v-model="filterStatus" :disabled="busy"><option value="">全部记录</option><option value="draft">我的草稿</option><option value="published">已发布</option></select></label><label>按类型筛选<select aria-label="按类型筛选" v-model="filterType" :disabled="busy"><option value="">全部类型</option><option v-for="t in types" :key="t.id" :value="t.id">{{t.name}}{{t.active?'':'（停用）'}}</option></select></label><button class="quiet" :disabled="busy" @click="filter">筛选记录</button>
          <p v-if="!records.length" class="muted">当前没有记录。</p><button v-for="r in records" :key="r.id" class="entry" :disabled="busy" @click="openRecord(r.id)"><strong>{{r.title}}</strong><small>{{r.type_name}} · {{r.status==='published'?'已发布（私人）':'草稿'}} · {{r.display_date}}</small></button>
          <div class="pagination"><button class="quiet" :disabled="busy||page<=1" @click="turnPage(page-1)">上一页</button><span>{{page}} / {{pages}} · {{total}}篇</span><button class="quiet" :disabled="busy||page>=pages" @click="turnPage(page+1)">下一页</button></div>
        </aside>
        <article class="card admin-editor">
          <p v-if="!record" class="muted">选择记录查看详情，或使用自己的内容类型新建。</p>
          <template v-else-if="recordMode==='view'">
            <div class="detail-heading"><h3>{{record.title}}</h3><a :href="'/admin/history/'+record.id">历史版本</a><a :href="'/preview/posts/'+record.id+'?revision='+record.revision" target="_blank" rel="noopener">前台预览</a><button :disabled="busy" @click="edit">编辑记录</button></div><p class="muted">{{record.display_date}} · {{record.status==='published'?'已发布，仅私人可见':'草稿'}}{{record.type_active?'':' · 类型已停用'}}</p>
            <ArticleBody class="markdown" :source="record.body" :format="record.body_format" namespace="admin-body"/>
            <section v-for="f in record.fields" :key="f.id" class="record-value"><h4>{{f.name}}{{f.active?'':'（停用字段，原值保留）'}}</h4><p v-if="f.description" class="muted">{{f.description}}</p><div v-if="f.kind==='markdown'" class="markdown" v-html="renderMarkdown(String(record.values[f.id||'']||''))"></div><p v-else class="plain-value">{{display(f,record.values[f.id||''])}}</p></section>
            <div class="tag-pills"><span v-for="t in record.tags" :key="t.id">#{{t.name}}</span></div><ConnectionsView :value="record.connections" @record="openRecord" />
            <button class="danger" :disabled="busy" @click="removeRecord">软删除记录</button>
          </template>
          <form v-else class="record-compose" @submit.prevent="saveRecord"><a v-if="record.id&&!immersive" :href="'/admin/history/'+record.id" @click="navigateTo('/admin/history/'+record.id,$event)">历史版本与安全恢复</a><fieldset :disabled="busy||itineraryPending"><h3>{{record.id?'编辑记录':'新建内容记录'}}</h3>
            <div class="save-toolbar workspace-save"><button type="button" class="workspace-publish" :disabled="placePending||uploadsPending||saveState.saving||saveState.status==='conflict'||saveState.uncertainCreation" @click="publishRecord">{{serverStatus==='published'?'更新发布':'发布文章'}}</button><p class="save-status" role="status" aria-live="polite" aria-atomic="true">{{saveLabels[saveState.status]}}<small v-if="saveState.completedAt">客户端完成时间 {{saveState.completedAt}}</small></p><button type="button" :disabled="placePending||uploadsPending||saveState.saving||saveState.status==='conflict'||saveState.uncertainCreation" @click="saveRecord" class="workspace-save-button">保存文章</button><button type="button" class="quiet" :disabled="saveState.saving||saveState.status==='conflict'||saveState.uncertainCreation" @click="openPreview">{{serverStatus==='published'?'真实预览已保存修订':'保存草稿并真实预览'}}</button></div>
            <p class="muted">{{immersive?(record.id?'草稿停笔自动保存；发布与已发布文章的修改需手动确认。':'请先手动保存草稿，之后停笔约3秒自动保存。'):'新记录先手动创建，已有草稿停笔约3秒自动保存全部字段。发布需手动保存；已发布内容不自动改写。'}}</p>
            <p v-if="serverStatus==='published'" class="published-warning">当前记录已发布：手动保存会更新读者可见的文章，预览不会替你保存或发布。</p>
            <section v-if="record.status==='published'&&['failed','needs_review'].includes(record.itinerary_generation?.status||'')" :class="record.itinerary_generation?.status==='failed'?'error':'notice'" :role="record.itinerary_generation?.status==='failed'?'alert':'status'"><p>{{record.itinerary_generation?.status==='failed'?'文章已发布；行程提取失败，原行程保留。':'文章已发布；自动行程需要校对。'}} {{record.itinerary_generation?.message}}</p><button type="button" class="quiet" @click="workspace='itinerary'">检查或重试行程</button></section>
            <section v-if="saveState.message" :class="saveState.status==='error'||saveState.status==='conflict'?'error':'notice'" :role="saveState.status==='error'||saveState.status==='conflict'?'alert':undefined"><p>{{saveState.message}}</p><p v-if="saveState.status==='conflict'">服务器可能已更新标题、正文、字段、关联或行程。本页输入仍保留，不会自动覆盖。</p><div class="actions"><span v-if="saveState.status==='conflict'">保留本页输入（自动保存已暂停）</span><a v-if="record.id&&saveState.status==='conflict'" :href="'/admin/history/'+record.id" target="_blank" rel="noopener">在新标签页查看服务器版本与历史</a><button v-if="record.id&&(saveState.status==='conflict'||saveState.code===404)" type="button" class="quiet" @click="reloadServer">重新加载服务器版本</button><a v-if="saveState.uncertainCreation" href="/admin/content" target="_blank" rel="noopener">在新标签页核对创建结果</a><a v-if="saveState.code===401" href="/login" target="_blank" rel="noopener">在新标签页重新登录</a><button v-if="saveState.status==='error'&&!saveState.uncertainCreation&&saveState.code!==404" type="button" class="quiet" @click="saveRecord">手动重试保存</button></div></section>
            <div  :class="[immersive?'writing-workspace':'legacy-compose',{'tools-hidden':!toolsOpen}]"><nav v-if="immersive" class="workspace-nav" aria-label="文章编辑模块"><button v-for="module in workspaceModules" :key="module.id" :data-workspace-module="module.id" type="button" :aria-current="workspace===module.id?'step':undefined" @click="workspace=module.id"><ModuleIcon :kind="module.id"/><span>{{module.name}}</span></button><button type="button" :aria-expanded="toolsOpen" @click="toolsOpen=!toolsOpen">{{toolsOpen?'收起辅助信息':'显示辅助信息'}}</button><ThemeOrnament placement="sidebar"/></nav><div class="workspace-main"><section v-show="!immersive||workspace==='basic'" class="writing-main" data-workspace-module="basic" aria-label="基本信息"><ModuleHeading v-if="immersive" kind="basic" title="基本信息" description="为故事命名，整理标签与旅行日期。"/><label>记录标题<input v-model="record.title" required maxlength="200" /></label><TagPicker :model-value="record.tags||[]" @update:model-value="record.tags=$event" :disabled="busy"/>
<section v-if="isFood" class="food-editor-fields" aria-label="餐厅信息"><h3>餐厅信息（均为可选）</h3><p>可记录餐厅、独立美食或家庭制作；不要求旅行来源，不以文章标题猜测店名。</p><ValueInput v-for="f in foodFields" :key="f.id" v-model="record.values[f.id!]" :field="f" :label="f.name" :disabled="busy"/><template v-if="!foodFields.length"><p>当前没有启用的餐厅字段；原文与历史值仍保留。</p><button v-if="!record.fields.some(f=>f.purpose)" type="button" :disabled="busy||dirty" @click="enableFoodFields">启用餐厅信息字段（请先保存当前修改）</button><p v-else>餐厅字段已在模板中停用；高级设置保留历史值，需要时在模板管理中明确启用。</p></template></section>
<p v-if="publishIntent" role="status">已进入发布确认：请检查正文和字段，再手动保存。此页面不会自动发布。</p><p v-if="record.marker_version===1" class="muted">历史标记兼容：@s 和 @t 保持原有地点含义；新增演出或交通请使用「@ 结构化记录」卡片。</p><div class="article-mode"><fieldset class="record-mode" :disabled="busy"><legend>记录模式</legend><label><input type="radio" name="article-record-mode" value="daily" :checked="!isTravel" @change="setRecordingMode('daily')"/>日常记录</label><label><input type="radio" name="article-record-mode" value="travel" :checked="isTravel" @change="setRecordingMode('travel')"/>旅行记录</label><small>切换模式保留正文、卡片、动态字段和历史行程。</small></fieldset><label v-if="record.article">文章结束日期（跨日可选）<input v-model="record.article.end_date" type="date" :min="record.display_date"/></label></div><section v-if="isTravel&&record.life" class="travel-essentials"><div class="editor-meta"><label>出发日期<input type="date" :value="record.life.start_date||(tripFields.start&&record.values[tripFields.start.id!])||''" @input="tripDate('start',($event.target as HTMLInputElement).value)"/></label><label>返回日期（可留空）<input type="date" :value="record.life.end_date||(tripFields.end&&record.values[tripFields.end.id!])||''" @input="tripDate('end',($event.target as HTMLInputElement).value)"/></label></div><section v-if="dateConflicts.length" role="alert" class="error"><p>历史日期存在冲突，尚未修改任何一方。动态字段：{{tripFields.start&&record.values[tripFields.start.id!]}} — {{tripFields.end&&record.values[tripFields.end.id!]}}；结构化日期：{{record.life.start_date}} — {{record.life.end_date}}</p><button type="button" @click="resolveDates('fields')">采用历史字段日期</button><button type="button" @click="resolveDates('life')">采用结构化日期</button></section><ValueInput v-if="tripFields.companions" v-model="record.values[tripFields.companions.id!]" :field="tripFields.companions" :label="tripFields.companions.name" :disabled="busy"/><details v-if="tripFields.lodging.some(f=>record?.values[f.id!])"><summary>历史住宿信息（原样保留）</summary><p v-for="f in tripFields.lodging" :key="f.id">{{record.values[f.id!]}}</p><p>新的住宿请在正文使用 @h 标记；这里不再单独填写。</p></details></section>
            </section><section v-show="!immersive||workspace==='body'" class="workspace-body" data-workspace-module="body" aria-label="正文编辑"><ModuleHeading v-if="immersive" kind="body" title="正文编辑" description="专注文字与照片，慢慢写下值得记住的生活。"/><button v-if="!immersive" type="button" class="quiet" :disabled="uploadsPending" @click="bodyPreview=!bodyPreview">{{bodyPreview?'返回正文编辑':'预览正文 Markdown'}}</button><TypographyPanel/><ArticleBody class="markdown" v-if="bodyPreview" :source="record.body" :format="record.body_format" namespace="editor-preview"/><BodyEditor v-else ref="bodyEditor" :record-id="record.id" :folder-id="record.media_folder_id" @uploaded="record.new_media_ids=[...(record.new_media_ids||[]),$event]" :title="record.title" :key="bodyEditorKey" v-model="record.body" :format="record.body_format||1" @update:format="record.body_format=$event" :disabled="busy||itineraryPending" @pending="uploadsPending=$event"><template #assistant><WritingAssistant :key="bodyEditorKey" :type-slug="types.find(t=>t.id===record!.type_id)?.slug||''" :template-slug="templates.find(t=>t.id===record!.template?.id)?.slug" :title="record.title" :display-date="record.display_date" :disabled="busy||itineraryPending||uploadsPending" :capture="()=>bodyEditor?.captureAI()||null" :apply="(id,text,mode)=>bodyEditor?.applyAI(id,text,mode)||false"/></template></BodyEditor>
            </section><LifeEditor :data-workspace-module="workspace==='itinerary'?'itinerary':'media'" :generation="record.itinerary_generation" @pending="itineraryPending=$event" @synchronized="openRecord($event.id)" v-show="!immersive||workspace==='media'||workspace==='itinerary'" :panel="immersive?(workspace==='itinerary'?'itinerary':'media'):undefined" v-if="record.life" :simple="true" :travel="isTravel" :date-fields="dateFields" :record-id="record.id" :revision="record.revision" :body="record.body" :unsaved="dirty" :value="record.life" :connections="lifeConnections" :disabled="busy||placePending||uploadsPending"/><EditorResources class="workspace-resource-card" data-workspace-module="media" v-show="!immersive||workspace==='media'" v-if="record" :record="record" :dirty="dirty" :disabled="busy||uploadsPending||placePending" @cover="setCover" @remove-media="removeMediaReference" @remove-place="record.connections.places=record.connections.places.filter(p=>p.id!==$event)" @remove-tag="record.tags=(record.tags||[]).filter(t=>t.id!==$event)" @changed="record?.id&&openRecord(record.id)"/><ConnectionsEditor :workspace-panel="immersive" data-workspace-module="relations" v-show="!immersive||workspace==='relations'" records-only :value="record.connections" :record-id="record.id" :disabled="busy"/><details v-show="!immersive||workspace==='publish'" class="writing-advanced" data-workspace-module="publish" open><summary><ModuleIcon v-if="immersive" kind="publish"/>发布设置 · 模板与自定义字段</summary><details class="writing-publication" :open="!immersive||publishIntent"><summary>展示日期与发布状态 · {{record.status==='draft'?'草稿':'私人发布'}}</summary><div class="editor-meta"><label>展示日期<input v-model="record.display_date" type="date" required /></label><label>记录状态<select aria-label="记录状态" v-model="record.status"><option value="draft">草稿</option><option value="published">发布（私人）</option></select></label></div></details><a v-if="immersive&&record.id" :href="'/admin/history/'+record.id" @click="navigateTo('/admin/history/'+record.id,$event)">历史版本与安全恢复</a><section class="writing-properties" aria-label="内容属性"><h3>内容属性与自定义字段</h3><label>列表摘要（选填，不在详情页重复展示）<textarea v-model="record.summary" maxlength="500" rows="3" placeholder="留空时自动从正文生成列表预览"/></label><p v-if="record.id" class="muted">当前使用保存时的字段配置，类型更新不会自动改写此记录。</p><button v-if="record.id&&(record.schema_version!==record.current_type_version||record.template&&record.template.version!==record.template.current_version)" type="button" class="quiet" @click="upgradeFields">使用最新字段配置</button>
            <fieldset v-for="group in groupedFields" :key="group.name" class="template-form-group"><legend>{{group.name}}</legend><section v-for="f in group.fields" :key="f.id" class="record-field" :data-field-id="f.id"><p v-if="f.description" class="muted">{{f.description}}</p>
              <ValueInput v-if="f.active" v-model="record.values[f.id||'']" :field="f" :label="f.name+(f.required?' *':'')" :disabled="busy" /><p v-else class="muted">{{f.name}}（已停用，原值保留）：{{display(f,record.values[f.id||''])}}</p>
            </section></fieldset>
            </section><details><summary>历史图片与地点关联（兼容设置）</summary><ConnectionsEditor @pending="placePending=$event" :value="record.connections" :record-id="record.id" :disabled="busy" /></details>
            </details></div><aside v-show="immersive&&toolsOpen" :data-workspace-module="workspace" class="workspace-context" aria-label="编辑辅助信息"><h3>{{workspaceModules.find(m=>m.id===workspace)?.name}}</h3><p>{{record.title||'尚未填写标题'}}</p><p>{{record.status==='draft'?'草稿 · 仅管理员可见':'私人发布'}}</p><p v-if="workspace==='body'">图片可直接粘贴、拖入或从媒体库插入。Esc 后按 Tab 可离开正文编辑区。</p><p v-if="workspace==='itinerary'">正文是叙事来源。人工活动与照片关联应保留，重新提取前请核对差异。</p><p>{{record.life?.activities.length||0}} 项行程 · {{lifeConnections.media.length}} 张图片</p></aside></div><div class="actions admin-save"><button type="submit" :disabled="placePending||uploadsPending||saveState.saving||saveState.status==='conflict'||saveState.uncertainCreation">保存记录</button><button v-if="record.id" type="button" class="quiet" @click="openRecord(record.id)">重新读取记录</button><span v-if="dirty" class="muted">有未保存的修改</span></div>
          </fieldset></form>
        </article>
      </div>
    </template>
    <RecordPreview v-if="previewRecord" :record="previewRecord" @close="previewRecord=null" />
  </section>
</template>

<style>
.food-editor-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:24px;min-width:0}.food-editor-fields>h3,.food-editor-fields>p,.food-editor-fields>template,.food-editor-fields>div:has(textarea){grid-column:1/-1}.writing-page .writing-main .food-editor-fields input:not([type=date]){font-size:16px;line-height:1.6;border:1px solid var(--line);border-radius:var(--radius,10px);padding:10px;background:var(--surface)}.food-editor-fields textarea{font-size:16px;min-height:110px}@media(max-width:600px){.food-editor-fields{grid-template-columns:1fr}}
</style>

<style scoped>
.new-record{display:flex;align-items:flex-start;gap:16px;flex-wrap:wrap}.record-mode{border:0;padding:0;margin:0;display:flex;gap:12px;flex-wrap:wrap;min-width:0}.record-mode legend{font-weight:650;margin-bottom:8px}.record-mode label{display:inline-flex;align-items:center;gap:8px;margin:0;cursor:pointer}.record-mode input[type=radio]{width:auto;accent-color:var(--accent)}.record-mode small{flex-basis:100%;color:var(--muted)}.advanced-record-type{width:100%;min-width:0}.advanced-record-type summary{cursor:pointer}.advanced-record-type select{max-width:100%}.article-mode .record-mode{margin-bottom:14px}
</style>
