<script setup lang="ts">
import { ref, computed, nextTick, defineAsyncComponent, onMounted, onUnmounted, inject } from 'vue'
import { routerKey } from 'vue-router'
import PrivatePreview from '../admin/PrivatePreview.vue'
import { request } from '../api'
import { renderMarkdown } from '../markdown'
const AdminContent=defineAsyncComponent(()=>import('../admin/AdminContent.vue'))
const routeRouter=inject(routerKey,undefined)
const adminAuthorized=ref(false)
const adminEnabled=ref(false), adminMode=ref(false)
const adminContent=ref<{canLeave:()=>boolean}|null>(null)
async function loadAdminAvailability(){try{const result=await request('/admin/status');if(logged.value){adminAuthorized.value=result?.is_admin===true;adminEnabled.value=result?.features?.dynamic_blog===true;adminMode.value=adminEnabled.value&&(window.location.hash==='#admin-content'||window.location.pathname==='/admin/content')}}catch{adminAuthorized.value=false;adminEnabled.value=false}}
function openAdmin(){if(!canLeave())return;resetEditor();adminMode.value=true;window.location.assign('/admin/content')}
function goBlog(){if(adminMode.value&&routeRouter){void routeRouter.push('/');return}if(adminMode.value&&adminContent.value&&!adminContent.value.canLeave())return;if(canLeave())window.location.assign('/')}
function closeAdmin(){if(routeRouter){void routeRouter.push('/journals');return}adminMode.value=false;window.location.assign('/journals')}

type Summary = { id:number; title:string; entry_date:string; category:string; tags:string[]; updated_at:string }
type Journal = Summary & { content:string }
type Photo = { id:string; filename:string }
type Page = { items:Summary[]; total:number; page:number; page_size:number }
const editorElement=ref<HTMLElement|null>(null)
const logged=ref(false), username=ref(''), password=ref(''), error=ref(''), notice=ref('')
const busy=ref(false), loading=ref(false), detailLoading=ref(false)
const journals=ref<Summary[]>([]), page=ref(1), total=ref(0), pageSize=20
const search=ref(''), from=ref(''), to=ref(''), categoryFilter=ref(''), tagFilter=ref('')
const categories=ref<string[]>([]), tags=ref<string[]>([])
const selected=ref<number|null>(null), title=ref(''), content=ref(''), entryDate=ref(today()), category=ref(''), tagText=ref('')
const editing=ref(true), preview=ref(false), photos=ref<Photo[]>([])
let detailGeneration=0, listGeneration=0
function today(){ return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date()) }
const draft=()=>JSON.stringify([title.value,content.value,entryDate.value,category.value,tagText.value])
const savedDraft=ref(draft())
const dirty=computed(()=>editing.value && draft()!==savedDraft.value)
const rendered=computed(()=>renderMarkdown(content.value))
const pages=computed(()=>Math.max(1,Math.ceil(total.value/pageSize)))
function canLeave(){return !busy.value && (!dirty.value || window.confirm('有未保存的修改，确定放弃吗？'))}
function clearImages(){detailGeneration++}
function resetEditor(){clearImages();selected.value=null;title.value='';content.value='';entryDate.value=today();category.value='';tagText.value='';photos.value=[];editing.value=true;preview.value=false;detailLoading.value=false;savedDraft.value=draft()}
async function revealEditor(){await nextTick();if(window.innerWidth<=760)editorElement.value?.scrollIntoView({behavior:'smooth',block:'start'})}
function newEntry(){if(canLeave()){resetEditor();error.value='';notice.value='';void revealEditor()}}
function fill(j:Journal){selected.value=j.id;title.value=j.title;content.value=j.content;entryDate.value=j.entry_date;category.value=j.category;tagText.value=j.tags.join('，');savedDraft.value=draft()}
async function load(){
  const generation=++listGeneration
  loading.value=true
  const params=new URLSearchParams({page:String(page.value),page_size:String(pageSize)})
  if(search.value.trim())params.set('q',search.value.trim())
  if(from.value)params.set('date_from',from.value)
  if(to.value)params.set('date_to',to.value)
  if(categoryFilter.value)params.set('category',categoryFilter.value)
  if(tagFilter.value)params.set('tag',tagFilter.value)
  try{
    const result=await request('/journals/page?'+params) as Page
    if(generation!==listGeneration || !logged.value)return
    total.value=result.total
    if(page.value>pages.value){page.value=pages.value;await load();return}
    journals.value=result.items
  }catch(e){if(generation===listGeneration)error.value=String(e)}
  finally{if(generation===listGeneration)loading.value=false}
}
async function loadFilters(){
  const result=await request('/journals/filters') as {categories:string[];tags:string[]}
  if(logged.value){categories.value=result.categories;tags.value=result.tags}
}
async function applyFilters(){if(!canLeave())return;resetEditor();page.value=1;error.value='';await load()}
async function turnPage(next:number){if(loading.value||next<1||next>pages.value||!canLeave())return;resetEditor();page.value=next;await load()}
async function loadPhotos(id:number,generation:number){
  const items=await request(`/journals/${id}/media`) as Photo[]
  if(generation!==detailGeneration)return
  photos.value=items

}
async function openEntry(id:number){
  if(!canLeave())return
  resetEditor();editing.value=false;detailLoading.value=true;error.value='';notice.value=''
  const generation=detailGeneration
  try{
    const j=await request('/journals/'+id) as Journal
    if(generation!==detailGeneration)return
    fill(j);detailLoading.value=false;void revealEditor()
    await loadPhotos(id,generation)
  }catch(e){if(generation===detailGeneration)error.value=String(e)}
  finally{if(generation===detailGeneration)detailLoading.value=false}
}
async function init(){
  try{const me=await request('/auth/me');username.value=me.username;logged.value=true}
  catch{return}
  await load();await loadAdminAvailability();try{await loadFilters()}catch(e){error.value=String(e)}
}
async function login(){
  if(busy.value)return
  error.value='';busy.value=true
  try{await request('/auth/login',{method:'POST',body:JSON.stringify({username:username.value,password:password.value})});password.value='';logged.value=true;page.value=1;await load();await loadFilters();await loadAdminAvailability()}
  catch(e){error.value=String(e)}finally{busy.value=false}
}
async function logout(){
  if(adminMode.value&&adminContent.value&&!adminContent.value.canLeave())return
  if(!canLeave())return
  busy.value=true
  try{await request('/auth/logout',{method:'POST'});expireSession()}
  catch(e){error.value=String(e)}finally{busy.value=false}
}
async function save(){
  if(busy.value)return
  error.value='';notice.value=''
  if(!entryDate.value){error.value='请选择日记日期';return}
  const values=tagText.value.split(/[,，]/).map(s=>s.trim()).filter(Boolean)
  const labels=[...new Set(values)]
  if(labels.length>10||labels.some(s=>s.length>40)){error.value='最多10个标签，每个标签不超过40字符';return}
  busy.value=true
  const generation=detailGeneration
  try{
    const j=await request(selected.value?'/journals/'+selected.value:'/journals',{
      method:selected.value?'PUT':'POST',body:JSON.stringify({title:title.value,content:content.value,entry_date:entryDate.value,category:category.value,tags:labels}),
    }) as Journal
    if(generation!==detailGeneration||!logged.value)return
    fill(j);editing.value=false;preview.value=false;notice.value='日记已保存'
    clearImages();photos.value=[]
    const photoGeneration=detailGeneration
    await load()
    try{await loadFilters();await loadPhotos(j.id,photoGeneration)}catch(e){error.value='日记已保存，但刷新失败：'+String(e)}
  }catch(e){if(generation===detailGeneration)error.value=String(e)}finally{busy.value=false}
}
async function cancelEdit(){
  if(!canLeave())return
  if(selected.value===null){resetEditor();return}
  editing.value=false
  await openEntry(selected.value)
}
async function remove(){
  if(busy.value||selected.value===null||!window.confirm('永久删除这篇旧版日记及其关联照片？旧版日记不进入回收站，无法通过回收站恢复。'))return
  busy.value=true;error.value=''
  const id=selected.value
  try{await request('/journals/'+id,{method:'DELETE'});resetEditor();notice.value='日记已删除';await load();await loadFilters()}
  catch(e){error.value=String(e)}finally{busy.value=false}
}
async function upload(e:Event){
  const input=e.target as HTMLInputElement, files=Array.from(input.files||[]), id=selected.value
  input.value=''
  if(id===null||busy.value||!files.length)return
  busy.value=true;error.value=''
  const generation=detailGeneration
  try{
    for(const file of files){const data=new FormData();data.append('file',file);await request(`/journals/${id}/media`,{method:'POST',body:data})}
  }catch(e){error.value=String(e)}
  finally{
    if(generation===detailGeneration){
      clearImages();photos.value=[]
      try{await loadPhotos(id,detailGeneration)}catch(e){error.value=String(e)}
    }
    busy.value=false
  }
}
function expireSession(){adminAuthorized.value=false;adminEnabled.value=false;adminMode.value=false;logged.value=false;listGeneration++;journals.value=[];categories.value=[];tags.value=[];total.value=0;search.value='';from.value='';to.value='';categoryFilter.value='';tagFilter.value='';notice.value='';resetEditor()}
function beforeUnload(e:BeforeUnloadEvent){if(dirty.value){e.preventDefault();e.returnValue=''}}
function sessionExpired(event:Event){queueMicrotask(()=>{if(!event.defaultPrevented)expireSession()})}
onMounted(()=>{window.addEventListener('session-expired',sessionExpired);window.addEventListener('beforeunload',beforeUnload);void init()})
onUnmounted(()=>{listGeneration++;clearImages();window.removeEventListener('session-expired',sessionExpired);window.removeEventListener('beforeunload',beforeUnload)})
</script>

<template>
  <main class="container">
    <header>
      <div><span class="eyebrow">{{adminMode?'创作与管理':'PRIVATE JOURNAL'}}</span><h1>{{adminMode?'内容工作室':'生活足迹'}} <span class="sub">Life Journal</span></h1></div>
      <div class="actions"><a v-if="logged&&adminAuthorized" href="/admin/maintenance">备份与恢复</a><button v-if="logged" class="quiet" :disabled="busy" @click="goBlog">私人Blog</button><button v-if="logged&&adminEnabled&&!adminMode" class="quiet" :disabled="busy" @click="openAdmin">内容管理后台</button><button v-if="logged" class="quiet" :disabled="busy" @click="logout">退出登录</button></div>
    </header>
    <p v-if="error" role="alert" class="error">{{error}}</p>
    <p v-if="notice" role="status" class="notice">{{notice}}</p>
    <section v-if="!logged" class="login card">
      <h2>欢迎回来</h2><p>你的日记，只属于你。</p>
      <form @submit.prevent="login">
        <label>用户名<input v-model="username" required autocomplete="username" maxlength="100" /></label>
        <label>密码<input v-model="password" type="password" required autocomplete="current-password" maxlength="1024" /></label>
        <button :disabled="busy">{{busy?'正在登录…':'登录私人空间'}}</button>
      </form>
    </section>
    <AdminContent v-else-if="adminMode&&adminEnabled" ref="adminContent" @exit="closeAdmin" />
    <section v-else class="layout">
      <aside class="card">
        <div class="asidehead"><h2>我的日记</h2><button :disabled="busy" @click="newEntry">+ 新建</button></div>
        <form class="filters" @submit.prevent="applyFilters">
          <label>搜索标题和正文<input v-model="search" type="search" maxlength="200" placeholder="输入关键词" /></label>
          <div class="date-range">
            <label>开始日期<input v-model="from" type="date" /></label>
            <label>结束日期<input v-model="to" type="date" :min="from || undefined" /></label>
          </div>
          <label>分类<select v-model="categoryFilter"><option value="">全部分类</option><option v-for="c in categories" :key="c">{{c}}</option></select></label>
          <label>标签<select v-model="tagFilter"><option value="">全部标签</option><option v-for="t in tags" :key="t">{{t}}</option></select></label>
          <button :disabled="busy||loading">筛选日记</button>
        </form>
        <p v-if="loading" role="status">正在加载日记…</p>
        <p v-else-if="!journals.length" class="muted">没有符合条件的日记，可以调整筛选或新建日记。</p>
        <nav aria-label="日记列表" :aria-busy="loading">
          <button v-for="j in journals" :key="j.id" class="entry" :class="{active:selected===j.id}" :aria-current="selected===j.id?'true':undefined" :disabled="busy||loading" @click="openEntry(j.id)">
            <strong>{{j.title}}</strong><small>{{j.entry_date}}<span v-if="j.category"> · {{j.category}}</span></small>
            <span v-if="j.tags.length" class="muted">{{j.tags.map(t=>'#'+t).join(' ')}}</span>
          </button>
        </nav>
        <div class="pagination" aria-label="日记分页">
          <button class="quiet" :disabled="busy||loading||page<=1" @click="turnPage(page-1)">上一页</button>
          <span>{{page}} / {{pages}} 页 · {{total}} 篇</span>
          <button class="quiet" :disabled="busy||loading||page>=pages" @click="turnPage(page+1)">下一页</button>
        </div>
      </aside>
      <article ref="editorElement" class="card editor" :aria-busy="detailLoading">
        <p v-if="detailLoading" role="status">正在读取日记…</p>
        <template v-else>
          <template v-if="editing">
            <h2>{{selected?'编辑日记':'写一篇日记'}}</h2>
            <form @submit.prevent="save">
              <fieldset :disabled="busy">
                <label>标题<input v-model="title" required maxlength="200" placeholder="给今天起个名字" /></label>
                <div class="editor-meta">
                  <label>日记日期<input v-model="entryDate" type="date" required /></label>
                  <label>分类<input v-model="category" maxlength="80" list="categories" placeholder="例如：日常" /></label>
                </div>
                <datalist id="categories"><option v-for="c in categories" :key="c" :value="c" /></datalist>
                <label>标签（逗号分隔，最多10个）<input v-model="tagText" placeholder="心情，阅读" /></label>
                <button type="button" class="quiet" :aria-pressed="preview" @click="preview=!preview">{{preview?'继续编辑':'预览 Markdown'}}</button>
                <div v-if="preview" class="markdown" v-html="rendered"></div>
                <label v-else>正文（Markdown）<textarea v-model="content" rows="15" maxlength="300000" placeholder="写下今天值得记住的事…" /></label>
                <div class="actions">
                  <button type="submit" :disabled="!title.trim()">{{busy?'正在保存…':selected?'保存修改':'保存日记'}}</button>
                  <button type="button" class="quiet" @click="cancelEdit">取消编辑</button>
                  <span v-if="dirty" class="muted">有未保存的修改</span>
                </div>
              </fieldset>
            </form>
          </template>
          <template v-else-if="selected">
            <div class="detail-heading"><h2>{{title}}</h2><button :disabled="busy" @click="editing=true">编辑日记</button></div>
            <p class="muted">{{entryDate}}<span v-if="category"> · {{category}}</span></p>
            <p v-if="tagText" class="tags">{{tagText}}</p>
            <div class="markdown" v-html="rendered"></div>
            <button class="danger" :disabled="busy" @click="remove">删除日记</button>
          </template>
          <div v-if="selected" class="photos">
            <h3>私人照片</h3>
            <label>上传照片<input type="file" accept="image/jpeg,image/png,image/webp" multiple :disabled="busy" @change="upload" /></label>
            <div class="photoGrid"><a v-for="p in photos" :key="p.id" :href="'/api/media/'+encodeURIComponent(p.id)" target="_blank" rel="noopener noreferrer"><PrivatePreview :id="p.id" :alt="p.filename" family="legacy" /></a></div>
          </div>
          <p v-else class="muted">保存日记后可以上传照片。</p>
        </template>
      </article>
    </section>
    <footer>仅供私人使用 · 请定期备份你的回忆</footer>
  </main>
</template>
