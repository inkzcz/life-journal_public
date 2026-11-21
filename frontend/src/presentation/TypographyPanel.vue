<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount} from 'vue'
import {request} from '../api'
import {defaults,saved,apply,loadTypography,type Typography} from './typography'
const draft=ref<Typography>(defaults()),error=ref(''),busy=ref(false),notice=ref(''),ready=ref(false)
let alive=true
const lines=[1,1.25,1.5,1.75,2],gaps=[0,4,8,12,16]
onMounted(async()=>{await loadTypography();if(alive){draft.value={...saved.value};ready.value=true}})
function cancel(){draft.value={...saved.value};apply(saved.value);error.value='';notice.value='已取消未保存排版'}
function reset(){draft.value={...defaults(),revision:saved.value.revision};apply(draft.value);notice.value='默认值已预览，保存后生效'}
async function save(){busy.value=true;error.value='';try{const {revision,...values}=draft.value;saved.value=await request('/admin/blog/typography',{method:'PUT',body:JSON.stringify({...values,expected_revision:revision})});draft.value={...saved.value};apply(saved.value);notice.value='全站排版已保存，文章原文与修订不变'}catch(e){error.value=String(e)}finally{busy.value=false}}
onBeforeUnmount(()=>{alive=false;apply(saved.value)})
</script>
<template><details class="typography-panel"><summary>排版设置 · 编辑工作区与阅读页</summary><p>全站显示偏好，不修改正文。阅读默认值保留旧文章外观；修改阅读偏好将影响所有文章。</p><fieldset :disabled="busy||!ready" @change="apply(draft);notice='未保存预览'"><legend>编辑器工作区</legend><label>编辑器行距<select aria-label="编辑器行距" v-model="draft.editor_line"><option v-for="n in lines" :value="n">{{n}}</option></select></label><label>编辑器段落间距<select aria-label="编辑器段落间距" v-model="draft.editor_gap"><option v-for="n in gaps" :value="n">{{n}}px</option></select></label></fieldset><fieldset :disabled="busy||!ready" @change="apply(draft);notice='未保存预览'"><legend>文章阅读页</legend><label>阅读行距<select aria-label="阅读行距" v-model="draft.reader_line"><option :value="null">保留原有默认值</option><option v-for="n in lines" :value="n">{{n}}</option></select></label><label>阅读段落间距<select aria-label="阅读段落间距" v-model="draft.reader_gap"><option :value="null">保留原有默认值</option><option v-for="n in gaps" :value="n">{{n}}px</option></select></label></fieldset><div class="actions"><button type="button" :disabled="busy||!ready" @click="save">保存排版</button><button type="button" :disabled="busy||!ready" class="quiet" @click="cancel">取消排版修改</button><button type="button" :disabled="busy||!ready" class="quiet" @click="reset">恢复默认排版</button></div><p role="status">{{notice}}</p><p v-if="error" role="alert">{{error}}；输入保留，请重新打开页面核对配置版本。</p></details></template>
<style scoped>.typography-panel{margin:12px 0;padding:12px;border:1px solid var(--line,var(--ui-line));background:var(--surface,transparent)}summary{cursor:pointer;min-height:36px}details[open]>summary{font-weight:700}fieldset{display:flex;flex-wrap:wrap;gap:12px;border:0;padding:8px 0}label{flex:1;min-width:130px}select{width:100%}.actions{display:flex;gap:8px;flex-wrap:wrap}</style>
