<script setup lang="ts">
import { ref,onMounted } from 'vue'
import {request} from '../api'
defineProps<{modelValue:string|null;disabled?:boolean;all?:boolean}>()
defineEmits<{(e:'update:modelValue',value:string):void}>()
const folders=ref<any[]>([])
async function reload(){folders.value=await request('/admin/archive/folders')}
function path(f:any,seen=new Set<string>()):string{if(seen.has(f.id))return f.name;seen.add(f.id);const parent=folders.value.find(p=>p.id===f.parent_id);return parent?path(parent,seen)+' / '+f.name:f.name}
onMounted(()=>void reload().catch(()=>{}));defineExpose({reload})
</script>
<template><select :value="modelValue||''" :disabled="disabled" @change="$emit('update:modelValue',($event.target as HTMLSelectElement).value)"><option v-if="all" value="*">所有文件夹</option><option value="">未分类</option><option v-for="f in folders" :key="f.id" :value="f.id">{{path(f)}}</option></select></template>
