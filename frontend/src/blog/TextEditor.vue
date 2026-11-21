<script setup lang="ts">
import {confirmAction} from '../ui/confirm'
import { ref,onMounted,onUnmounted,computed } from 'vue'
import { request } from '../api'
import { applyText } from './siteText'
const data=ref<{values:Record<string,string>;defaults:Record<string,string>;revision:number;site_name:string;layout_revision:number}|null>(null),values=ref<Record<string,string>>({}),saved=ref(''),title=ref(''),savedTitle=ref(''),error=ref(''),busy=ref(false)
let alive=true
onUnmounted(()=>{alive=false})
const dirty=computed(()=>JSON.stringify(values.value)!==saved.value||title.value!==savedTitle.value)
const names:Record<string,string>={'site.subtitle':'网站副标题','home.welcome':'首页欢迎语与主要标题','home.introduction':'首页介绍','footer.description':'页脚说明','footer.copyright':'版权文字'}
function adopt(d:any){data.value=d;title.value=d.site_name;savedTitle.value=d.site_name;values.value={...d.values};saved.value=JSON.stringify(values.value);applyText(d)}
async function load(){try{const d=await request('/site/text');if(alive)adopt(d)}catch(e){if(alive)error.value=String(e)}}
async function save(){busy.value=true;error.value='';try{adopt(await request('/admin/site/text',{method:'PUT',body:JSON.stringify({title:title.value,expected_layout_revision:data.value!.layout_revision,expected_revision:data.value!.revision,values:values.value})}))}catch(e){error.value=String(e)}finally{busy.value=false}}
async function reset(){if(await confirmAction('将网站名称及全部主要文字恢复默认（待保存），不影响主题、文章、首页模块或安全提示。确定吗？')){values.value={};title.value='Life Journal'}}
async function canLeave(){return !busy.value&&(!dirty.value||await confirmAction('有未保存的文字修改，确定放弃吗？'))}
defineExpose({canLeave,isDirty:()=>dirty.value})
onMounted(load)
</script>
<template><section class="card"><h2>文字自定义</h2><p>网站名称复用现有站点配置；栏目名称在栏目或导航中设置。以下仅改变显示文字，不改变地址、权限、操作按钮和安全警告。空项跟随默认。首页欢迎语与介绍仅覆盖首个启用的网站介绍模块；其它模块仍使用自身文案。</p><p v-if="error" class="error" role="alert">{{error}}</p><form v-if="data" @submit.prevent="save"><fieldset :disabled="busy"><label>网站名称<input v-model="title" required maxlength="100" /></label><button type="button" class="quiet" @click="title='Life Journal'">网站名称恢复默认</button><div v-for="(fallback,key) in data.defaults" :key="key"><label>{{names[key]||(key.startsWith('admin.')?'后台导航 · ':key.startsWith('nav.')?'前台导航 · ':'页面标题 · ')+String(fallback)}}<input :value="values[key]||''" :placeholder="key==='home.welcome'||key==='home.introduction'?'留空：沿用首页模块当前文案':String(fallback)" :maxlength="key==='home.introduction'||key==='footer.description'?2000:200" @input="(e)=>{const v=(e.target as HTMLInputElement).value;if(v)values[key]=v;else delete values[key]}" /></label><button type="button" class="quiet" @click="delete values[key]">单项恢复默认</button></div><p role="status">{{dirty?'有未保存的文字修改':'显示已保存配置'}}</p><div class="actions"><button>保存文字</button><button type="button" class="quiet" @click="values=JSON.parse(saved);title=savedTitle">取消修改</button><button type="button" class="quiet" @click="reset">全部文字恢复默认（待保存）</button><button type="button" class="quiet" @click="async()=>{if(await canLeave())await load()}">重新读取已保存文字</button></div></fieldset></form></section></template>
