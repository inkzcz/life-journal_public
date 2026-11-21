<script setup lang="ts">
import {ref,defineAsyncComponent} from 'vue'
import type {Appearance} from '../blog/types'
import ThemeBoundary from './ThemeBoundary.vue'
import ManagementFrame from './ManagementFrame.vue'
import UiButton from './UiButton.vue'
import UiPanel from './UiPanel.vue'
import {confirmAction} from './confirm'
const WritePage=defineAsyncComponent(()=>import('../writing/WritePage.vue'))
const ContentPage=defineAsyncComponent(()=>import('../admin/ContentPage.vue'))
const LoginPage=defineAsyncComponent(()=>import('../blog/LoginPage.vue'))
defineProps<{appearance:Appearance;recordId?:string}>()
const view=ref('blog')
</script>
<template><section class="cross-page-preview" aria-label="跨页面外观预览"><div class="ui-toolbar" role="tablist" aria-label="预览区域"><UiButton v-for="[key,name] in [['blog','Blog阅读'],['writing','写作工作台'],['admin','Admin后台'],['login','登录页']]" :key="key" :variant="view===key?'primary':'secondary'" role="tab" :aria-selected="view===key" @click="view=key">{{name}}</UiButton><UiButton variant="secondary" @click="confirmAction('主题确认弹窗预览。确认或取消均不会修改任何数据。')">预览确认弹窗</UiButton></div><p>以下为真实组件的只读投影；不能上传、保存文章或登录，不提交外观配置。</p><ThemeBoundary :appearance="appearance" class="preview-surface"><slot v-if="view==='blog'"/><div v-else-if="view==='writing'" inert><WritePage :preview="appearance" :preview-record-id="recordId"/></div><ManagementFrame v-else-if="view==='admin'" preview><ContentPage preview-only/></ManagementFrame><div v-else inert><LoginPage preview/></div></ThemeBoundary><UiPanel title="预览与保存"><p>预览使用同一组Token。取消恢复已保存配置；只有“保存外观”会写入服务器。</p></UiPanel></section></template>
<style scoped>.cross-page-preview{min-width:0}.ui-toolbar{margin-block:16px}.preview-surface{border:1px solid var(--ui-line);border-radius:var(--ui-radius);overflow:hidden}.preview-surface :deep(.studio){grid-template-columns:180px minmax(0,1fr)}.preview-surface :deep(.studio-sidebar){position:static;height:auto}.preview-surface :deep(.writing-workspace){grid-template-columns:160px minmax(0,1fr)}.preview-surface :deep(.workspace-context){display:none}@media(max-width:900px){.preview-surface :deep(.studio){display:block}.preview-surface :deep(.writing-workspace){display:block}}</style>
