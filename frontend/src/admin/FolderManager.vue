<script setup lang="ts">
import {confirmAction} from '../ui/confirm'
import {ref,onMounted} from 'vue'
import {request} from '../api'
import FolderSelect from './FolderSelect.vue'
const emit=defineEmits<{(e:'changed'):void}>()
const folders=ref<any[]>([]),draft=ref<any>({name:'',parent_id:''}),error=ref(''),busy=ref(false),generation=ref(0)
async function load(){folders.value=await request('/admin/archive/folders');generation.value++}
async function save(){if(busy.value)return;busy.value=true;error.value='';try{const d=draft.value;await request('/admin/archive/folders'+(d.id?'/'+d.id:''),{method:d.id?'PUT':'POST',body:JSON.stringify({name:d.name,parent_id:d.parent_id||null,...(d.id?{expected_revision:d.revision}:{})})});draft.value={name:'',parent_id:''};await load();emit('changed')}catch(e){error.value=String(e)}finally{busy.value=false}}
async function remove(){if(!draft.value.id||!await confirmAction('仅删除空逻辑文件夹，不删除图片。继续吗？'))return;busy.value=true;try{await request('/admin/archive/folders/'+draft.value.id,{method:'DELETE',body:JSON.stringify({expected_revision:draft.value.revision})});draft.value={name:'',parent_id:''};await load();emit('changed')}catch(e){error.value=String(e)}finally{busy.value=false}}
onMounted(()=>void load().catch(e=>error.value=String(e)))
</script>
<template><details class="card"><summary>管理逻辑文件夹</summary><p>移动分类不会改变图片UUID或文件路径；只能删除空文件夹。</p><p v-if="error" role="alert">{{error}}</p><label>选择要编辑的文件夹<select aria-label="选择要编辑的文件夹" :value="draft.id||''" :disabled="busy" @change="draft=JSON.parse(JSON.stringify(folders.find(f=>f.id===($event.target as HTMLSelectElement).value)||{name:'',parent_id:''}))"><option value="">新建文件夹</option><option v-for="f in folders" :key="f.id" :value="f.id">{{f.name}}</option></select></label><label>文件夹名称<input v-model="draft.name" maxlength="100" :disabled="busy"/></label><label>上级文件夹<FolderSelect aria-label="上级文件夹" :key="generation" v-model="draft.parent_id" :disabled="busy"/></label><div class="actions"><button type="button" :disabled="busy||!draft.name.trim()" @click="save">保存文件夹</button><button v-if="draft.id" type="button" class="danger" :disabled="busy" @click="remove">删除空文件夹</button></div></details></template>
