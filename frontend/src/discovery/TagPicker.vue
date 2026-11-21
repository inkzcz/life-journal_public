<script setup lang="ts">
import {ref,watch,onUnmounted} from 'vue'
import {request} from '../api'
export type Tag={id:string;name:string}
const props=defineProps<{modelValue:Tag[];disabled?:boolean}>(),emit=defineEmits<{(e:'update:modelValue',v:Tag[]):void}>()
const q=ref(''),items=ref<Tag[]>([]),error=ref(''),composing=ref(false),creating=ref(false)
let generation=0,timer:ReturnType<typeof setTimeout>|undefined
watch(q,()=>{clearTimeout(timer);const g=++generation;timer=setTimeout(async()=>{try{const d=await request('/admin/tags?q='+encodeURIComponent(q.value));if(g===generation)items.value=d.items}catch(e){if(g===generation)error.value=String(e)}},250)},{immediate:true})
function add(t:Tag){if(props.disabled||props.modelValue.length>=10||props.modelValue.some(x=>x.id===t.id))return;emit('update:modelValue',[...props.modelValue,t]);q.value=''}
async function create(){if(composing.value||creating.value||props.disabled||!q.value.trim())return;creating.value=true;error.value='';try{add(await request('/admin/tags',{method:'POST',body:JSON.stringify({name:q.value})}))}catch(e){error.value=String(e)}finally{creating.value=false}}
onUnmounted(()=>{generation++;clearTimeout(timer)})
</script>
<template><fieldset class="tag-picker" :disabled="disabled"><legend>标签 · {{modelValue.length}} / 10</legend><p class="muted">搜索并选择已有标签，或明确创建新标签。标签会随草稿一起保存。</p><ul class="tag-pills"><li v-for="t in modelValue" :key="t.id"><span>{{t.name}}</span><button type="button" class="quiet" :aria-label="'移除标签'+t.name" @click="emit('update:modelValue',modelValue.filter(x=>x.id!==t.id))">×</button></li></ul><label>搜索标签<input v-model="q" maxlength="40" @compositionstart="composing=true" @compositionend="composing=false" @keydown.enter.prevent="!$event.isComposing&&!composing&&create()" /></label><div class="tag-options"><button v-for="t in items.filter(t=>!modelValue.some(x=>x.id===t.id))" :key="t.id" type="button" class="quiet" :disabled="modelValue.length>=10" @click="add(t)">{{t.name}}</button></div><button type="button" class="quiet" :disabled="creating||composing||!q.trim()||modelValue.length>=10" @click="create">创建标签「{{q}}」</button><p v-if="error" role="alert">{{error}}</p></fieldset></template>
