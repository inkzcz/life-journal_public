<script setup lang="ts">
import {ref} from 'vue'
import AIAdmin from '../exchange/AIAdmin.vue'
import WritingAssistant from '../exchange/WritingAssistant.vue'
import ConfirmHost from '../ui/ConfirmHost.vue'
import {rememberAppearance} from '../ui/theme'
import {withColors} from '../blog/colors'
import {blankSite} from '../blog/types'
const page=ref('admin'),dark=ref(false)
function theme(){dark.value=!dark.value;rememberAppearance(withColors({...blankSite().appearance,style:'editorial',palette:'lilac',mode:dark.value?'dark':'light'},dark.value?'dark':'light',dark.value?{card_background:'#302a38',body_text:'#f5eefb',accent:'#d0b8f0'}:{card_background:'#fffaff',body_text:'#493d59',accent:'#65479a'}))}
function capture(){return {id:'synthetic-anchor',body:'此为合成验收正文，没有私人记录。',selection:'合成选区',mode:'source' as const,format:2 as const}}
</script>
<template><header class="ai-preview-header"><h1>AI 合成验收</h1><p>真实生产组件，配置仅在浏览器内存中，不访问真实 API，不使用密钥，不发送付费请求。</p><nav aria-label="合成验收导航"><button @click="page='admin'">服务商与模型管理</button><button @click="page='assistant'">写作任务默认值</button><button @click="theme">切换自定义配色</button></nav></header><AIAdmin v-if="page==='admin'"/><div v-else class="ai-preview-assistant"><WritingAssistant type-slug="synthetic" title="合成验收文章" display-date="2000-01-01" :capture="capture" :apply="()=>false"/></div><ConfirmHost/></template>
<style scoped>.ai-preview-header,.ai-preview-assistant{max-width:1160px;margin:auto;padding:16px;min-width:0}.ai-preview-header nav{display:flex;flex-wrap:wrap;gap:8px}.ai-preview-header p{overflow-wrap:anywhere}</style>
