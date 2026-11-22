<script setup lang="ts">
import {ref} from 'vue'
import EntryCard from '../writing/EntryCard.vue'
import PrivatePreview from '../admin/PrivatePreview.vue'
import AdminContent from '../admin/AdminContent.vue'
import CalendarPage from '../calendar/CalendarPage.vue'
import {rememberAppearance} from '../ui/theme'
import {blankSite} from '../blog/types'
import type {Entry} from '../writing/entries'
const page=ref('cards'),dark=ref(false)
function toggle(){dark.value=!dark.value;rememberAppearance({...blankSite().appearance,style:'editorial',palette:'celadon',mode:dark.value?'dark':'light'})}
const photo='22222222-2222-4222-8222-222222222222'
const samples:Entry[]=[
 {id:'10000000-0000-4000-8000-000000000001',kind:'l',name:'午后，沿着湖边慢慢走',fields:{date:'2026-11-22',description:'没有赶路的下午，记下一阵风和水面的光。此为虚构验收内容。'},media_ids:[photo]},
 {id:'10000000-0000-4000-8000-000000000002',kind:'f',name:'一顿温热的家常晚餐',fields:{date:'2026-11-22',review:'口味清淡，刚刚好。\n好好吃饭，也是一种生活记录。'},media_ids:[]},
 {id:'10000000-0000-4000-8000-000000000003',kind:'m',name:'电影 · 周末的光',fields:{date:'2026-11-22',time:'19:30',cinema:'合成影院 · 安静的三号影厅',screen:'3号厅',seat:'6排8座',rating:'4 / 5',review:'散场以后，还想留住最后一幕的温柔。电影名称与影院均为虚构。'},media_ids:[photo]},
 {id:'10000000-0000-4000-8000-000000000004',kind:'s',name:'夜晚的小型音乐会',fields:{show_type:'音乐现场',performer:'合成演出者',date:'2026-11-22',time:'20:00',venue:'合成场馆：用于检验长名称在移动端的自然换行与完整展示',seat:'自由入座',review:'把这个声音，留在今天。'},media_ids:[]},
 {id:'10000000-0000-4000-8000-000000000005',kind:'g',name:'一份用心准备的小礼物',fields:{direction:'收到',person:'合成友人',date:'2026-11-22',occasion:'平常的一天',description:'不需要盛大的理由，也值得记下来。'},media_ids:[]},
 {id:'10000000-0000-4000-8000-000000000006',kind:'t',name:'合成车次 G0000',fields:{transport_type:'高铁',departure:'合成起点',destination:'合成终点',departure_at:'2026-11-22T08:00+08:00',arrival_at:'2026-11-22T10:00+08:00',departure_zone:'Asia/Shanghai',arrival_zone:'Asia/Shanghai',seat:'05车08A',description:'沿途经过的景色，也是一段记忆。'},media_ids:[]},
]
</script>
<template><div class="synthetic-preview"><header class="preview-header"><p class="eyebrow">LIFE JOURNAL · v5.1.10</p><h1>写下生活，也留住细节</h1><p>合成验收预览：所有内容仅保存在浏览器内存，刷新即重置；不会请求真实 API 或发送通知。</p><nav aria-label="验收页面"><button @click="page='cards'" :aria-pressed="page==='cards'">六类生活卡片</button><button @click="page='writing'" :aria-pressed="page==='writing'">日常与旅行写作</button><button @click="page='notification'" :aria-pressed="page==='notification'">通知配置</button><button class="quiet" @click="toggle">{{dark?'切换浅色':'切换深色'}}</button></nav></header><div v-if="page==='cards'" class="preview-card-grid"><EntryCard v-for="entry in samples" :key="entry.id" :entry="entry"><template #media><div class="entry-thumbnails"><PrivatePreview v-for="id in entry.media_ids" :key="id" :id="id" alt="合成验收封面" :eager="true"/></div></template></EntryCard></div><AdminContent v-else-if="page==='writing'" :immersive="true"/><CalendarPage v-else/></div></template>
<style scoped>.synthetic-preview{max-width:1200px;margin:auto;padding:24px;min-width:0}.preview-header{display:block;max-width:800px;padding:18px 0 28px}.preview-header h1{font-size:clamp(26px,5vw,42px);line-height:1.3}.preview-header p{line-height:1.7;color:var(--muted);overflow-wrap:anywhere}.preview-header nav{display:flex;gap:8px;flex-wrap:wrap}.preview-header button{font-size:13px}.preview-card-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start;gap:16px}.preview-card-grid :deep(.life-entry-card){margin:0}@media(max-width:720px){.synthetic-preview{padding:16px}.preview-card-grid{grid-template-columns:1fr}.preview-header nav button{flex:1 1 40%}}</style>
