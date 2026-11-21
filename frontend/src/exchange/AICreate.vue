<script setup lang="ts">
import {ref,computed,onMounted} from 'vue'
import {onBeforeRouteLeave} from 'vue-router'
import {request} from '../api'
import {newId} from '../ids'
import {confirmAction} from '../ui/confirm'
import WritingAssistant from './WritingAssistant.vue'
import ImportAdmin from './ImportAdmin.vue'
import type {TypeSummary} from '../admin/types'
const types=ref<TypeSummary[]>([]),templates=ref<any[]>([]),type=ref(''),template=ref(''),job=ref(''),completed=ref(false),pending=ref(false),unsent=ref(false),error=ref('')
const selected=computed(()=>types.value.find(t=>t.slug===type.value))
const applicable=computed(()=>templates.value.filter(t=>t.active&&t.type_id===selected.value?.id))
function captureNew(){return {id:newId(),body:'',selection:'',mode:'source' as const,format:2}}
function typeChanged(){template.value=''}
onMounted(async()=>{try{const [t,p]=await Promise.all([request('/admin/content/types'),request('/admin/templates')]);types.value=t;templates.value=p;type.value=t.find((v:TypeSummary)=>v.active)?.slug||''}catch(e){error.value=String(e)}})
onBeforeRouteLeave(async()=>completed.value||(!job.value&&!pending.value&&!unsent.value)||await confirmAction('离开AI创作工作台？尚未发送的素材或未校验映射可能丢失；生成中的调用可能仍计费。服务器已保存的候选可从图文导入恢复。'))
</script>
<template><main class="container ai-create"><header><RouterLink to="/write">返回普通写作</RouterLink><h1>AI 创作新文章</h1><p>选择你自己的内容类型与模板，确认发送范围后生成候选。逐项修正并校验后仅创建新草稿，不覆盖已有文章，不自动发布。</p></header><p v-if="error" role="alert" class="error">{{error}}</p><section class="card"><h2>选择文章结构</h2><label>内容类型<select aria-label="AI创作内容类型" v-model="type" :disabled="!!job||pending" @change="typeChanged"><option v-for="t in types.filter(t=>t.active)" :key="t.id" :value="t.slug">{{t.name}}</option></select></label><label>适用模板<select aria-label="AI创作模板" v-model="template" :disabled="!!job||pending"><option value="">通用布局</option><option v-for="t in applicable" :key="t.id" :value="t.slug">{{t.name}}</option></select></label><p>仅使用所选类型当前真实字段、选项及验证规则；素材未说明的信息应留空，缺失必填信息在候选中人工补齐。</p></section><WritingAssistant v-if="type&&!job" creation :type-slug="type" :template-slug="template||undefined" title="" display-date="" :capture="captureNew" :apply="()=>false" @dirty="unsent=$event" @pending="pending=$event" @preview="job=$event"/><ImportAdmin v-if="job" :key="job" :initial-job-id="job" @completed="completed=true"/><p><RouterLink to="/admin/import">无模型？下载 ChatGPT 网页版规范或离线导入图文</RouterLink></p></main></template>
<style scoped>.ai-create{max-width:1100px;min-width:0}.ai-create header{display:block}.ai-create>section{margin-block:20px;padding:20px}.ai-create label{display:block;margin-block:12px}.ai-create select{max-width:100%}.ai-create :deep(.exchange-admin){padding-inline:0}</style>
