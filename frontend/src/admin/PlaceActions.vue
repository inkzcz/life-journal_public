<script setup lang="ts">
import {confirmAction} from '../ui/confirm'
import {ref} from 'vue'
import {request} from '../api'
const props=defineProps<{place:any;disabled:boolean}>(),emit=defineEmits<{(e:'changed'):void;(e:'busy',value:boolean):void}>()
const candidates=ref<any[]>([]),target=ref<any>(null),preview=ref<any>(null),error=ref(''),busy=ref(false)
async function run(fn:()=>Promise<void>){if(busy.value)return;busy.value=true;emit('busy',true);error.value='';try{await fn()}catch(e){error.value=String(e)}finally{busy.value=false;emit('busy',false)}}
async function remove(){if(!await confirmAction('直接删除此地点？不进入回收站；任何当前或历史引用都会阻止删除。'))return;void run(async()=>{await request('/admin/archive/places/'+props.place.id,{method:'DELETE',body:JSON.stringify({expected_revision:props.place.revision})});emit('changed')})}
function find(){void run(async()=>{candidates.value=await request('/admin/archive/places/'+props.place.id+'/duplicates')})}
function choose(p:any){void run(async()=>{target.value=p;preview.value=await request('/admin/archive/places/'+props.place.id+'/merge-preview?target_id='+p.id)})}
async function merge(){if(!preview.value||!await confirmAction('确认合并到「'+target.value.name+'」？当前文章将生成新修订；旧地点UUID和历史保留，操作不能用简单取消撤销。'))return;void run(async()=>{await request('/admin/archive/places/'+props.place.id+'/merge',{method:'POST',body:JSON.stringify({target_id:target.value.id,expected_revision:preview.value.source.revision,target_revision:preview.value.target.revision,confirmation:'合并地点'})});preview.value=null;emit('changed')})}
</script>
<template><section><p v-if="error" class="error" role="alert">{{error}}</p><p v-if="place.merged_into">此地点已合并，历史UUID保留。目标：{{place.merged_into}}</p><button class="danger" :disabled="disabled||busy" @click="remove">直接删除未引用地点</button><details v-if="!place.merged_into"><summary>识别与合并重复地点（本地）</summary><p>同名且城市、国家相容的地点仅作为候选；不会自动合并，不联网查询。</p><button :disabled="disabled||busy" @click="find">查找重复候选</button><button v-for="p in candidates" :key="p.id" class="entry" :disabled="disabled||busy" @click="choose(p)">{{p.name}} · {{p.city}} · {{p.address}} · {{p.id}}</button><section v-if="preview"><h4>合并预览</h4><p>源：{{preview.source.id}} → 目标：{{preview.target.id}}</p><p v-for="(r,i) in preview.references" :key="i">{{r.kind}} · {{r.title}}{{r.revision?' · 修订'+r.revision:''}}</p><p>当前引用迁移到目标，历史快照保持原样；旧身份不会被删除。</p><button class="danger" :disabled="disabled||busy" @click="merge">确认合并地点</button><button class="quiet" :disabled="busy" @click="preview=null">取消预览</button></section></details></section></template>
