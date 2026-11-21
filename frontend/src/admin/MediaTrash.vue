<script setup lang="ts">
import {confirmAction,promptAction} from '../ui/confirm'
import {newId} from '../ids'
import {ref,onMounted,onBeforeUnmount} from 'vue'
import {request} from '../api'
import PrivatePreview from './PrivatePreview.vue'
const rows=ref<any[]>([]),selected=ref<string[]>([]),detail=ref<any>(null),ops=ref<any[]>([]),results=ref<any[]>([]),busy=ref(false),error=ref(''),page=ref(1),opPage=ref(1),total=ref(0),key=ref('')
async function load(){const [data,jobs]=await Promise.all([request('/admin/archive/media-trash?page='+page.value),request('/admin/archive/media-purge-operations?page='+opPage.value)]);rows.value=data.items;total.value=data.total;ops.value=jobs;selected.value=[]}
async function show(id:string){try{detail.value=await request('/admin/archive/media-trash/'+id)}catch(e){error.value=String(e)}}
async function execute(action:'restore'|'purge'){
 if(busy.value||!selected.value.length)return
 const count=selected.value.length
 if(!await confirmAction(action==='purge'?'永久删除所选'+count+'张图片的原图、预览与缩略图？已有备份不会自动清除。被任何历史或当前内容引用的图片会拒绝。':'恢复所选'+count+'张图片？'))return
 if(action==='purge'&&await promptAction('二次确认：请输入图片数量 '+count)!==String(count))return
 busy.value=true;error.value='';key.value=key.value||newId()
 try{const result=await request('/admin/archive/media-trash/actions',{method:'POST',body:JSON.stringify({action,request_key:key.value,confirmation:action==='purge'?'永久删除图片':'恢复图片',confirm_count:count,items:rows.value.filter(r=>selected.value.includes(r.id)).map(r=>({id:r.id,expected_revision:r.revision}))})});results.value=result.items;key.value='';detail.value=null;await load()}catch(e){error.value=String(e)+'；结果未确认，请保持所选项重试原请求或核对操作日志。'}finally{busy.value=false}
}
async function resume(op:any,action:'retry'|'cancel'){
 if(busy.value||!await confirmAction(action==='retry'?'明确继续此永久删除操作？已提交的删除只能完成清理，不能恢复。':'取消数据库提交前的删除，文件将回到媒体回收站。继续吗？'))return
 busy.value=true;error.value='';try{await request('/admin/archive/media-purge-operations/'+op.id,{method:'POST',body:JSON.stringify({action,confirmation:action==='retry'?'继续永久删除':'取消删除'})});await load()}catch(e){error.value=String(e)}finally{busy.value=false}
}
function leave(e:BeforeUnloadEvent){if(busy.value){e.preventDefault();e.returnValue=''}}
onMounted(()=>{void load().catch(e=>error.value=String(e));window.addEventListener('beforeunload',leave)});onBeforeUnmount(()=>window.removeEventListener('beforeunload',leave));defineExpose({canLeave:()=>!busy.value})
</script>
<template><section class="media-trash card"><h3>图片回收站与删除日志</h3><p>媒体自动清理默认关闭。恢复不复制文件；永久删除检查当前文章、软删除文章、全部历史修订、行程、照片注记和栏目引用。原有备份不会随当前删除而消失。</p><p v-if="error" role="alert" class="error">{{error}}</p><p v-if="busy" role="status">正在处理，请勿关闭页面；中断后请查看操作日志，不要假定已经完成。</p><div class="actions"><button :disabled="busy" @click="selected=rows.map(r=>r.id)">全选当前页</button><button :disabled="busy||!selected.length" @click="execute('restore')">恢复所选图片</button><button class="danger" :disabled="busy||!selected.length" @click="execute('purge')">永久删除所选图片</button></div><div class="trash-grid"><article v-for="row in rows" :key="row.id"><label class="checks"><input v-model="selected" type="checkbox" :value="row.id" :disabled="busy"/>{{row.title||row.filename}}</label><PrivatePreview v-if="!row.purge_operation_id" family="trash" :id="row.id" :alt="row.alt"/><p v-else>文件删除处理中，预览暂停；请查看日志。</p><button class="quiet" :disabled="busy" @click="show(row.id)">查看引用来源</button></article></div><p v-if="!rows.length">图片回收站为空。</p><div class="actions"><button :disabled="busy||page<=1" @click="page--;load()">上一页</button><span>{{page}} / {{Math.max(1,Math.ceil(total/24))}}</span><button :disabled="busy||page*24>=total" @click="page++;load()">下一页</button></div><section v-if="detail"><h4>引用来源：{{detail.title||detail.filename}}</h4><p v-if="!detail.references.length">当前无引用；永久删除前服务端仍会在锁内复核。</p><p v-for="(r,i) in detail.references" :key="i">{{r.kind}} · {{r.title}} {{r.revision?'· 修订'+r.revision:''}}{{r.deleted?'（文章已软删除）':''}}</p></section><section v-if="results.length"><h4>逐项结果</h4><p v-for="r in results" :key="r.media_id">{{r.media_id}} · {{r.state}} · {{typeof r.reason==='object'?r.reason.message:r.reason||''}}</p></section><details open><summary>文件操作日志（不会在启动时自动重放）</summary><div class="actions"><button :disabled="busy||opPage<=1" @click="opPage--;load()">较新日志</button><span>第{{opPage}}页</span><button :disabled="busy||ops.length<100" @click="opPage++;load()">较早日志</button></div><p v-for="op in ops" :key="op.id">{{op.media_id}} · {{op.state}} {{op.error_code}} <button v-if="!['completed','cancelled'].includes(op.state)" class="quiet" :disabled="busy" @click="resume(op,'retry')">重试原删除</button><button v-if="['prepared','isolated'].includes(op.state)" class="quiet" :disabled="busy" @click="resume(op,'cancel')">取消未提交删除</button></p></details></section></template>
<style scoped>.trash-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.trash-grid article{min-width:0;overflow-wrap:anywhere}.trash-grid img{max-width:100%;aspect-ratio:1.5;object-fit:cover}.media-trash p{overflow-wrap:anywhere}.checks input{width:auto}@media(max-width:600px){.trash-grid{grid-template-columns:1fr}}</style>
