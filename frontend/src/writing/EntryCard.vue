<script setup lang="ts">
import {computed} from 'vue'
import {entryNames,entryFields,type Entry} from './entries'

const props=withDefaults(defineProps<{entry:Entry;heading?:'h2'|'h3'}>(),{heading:'h3'})
const notes=new Set(['review','description'])
const compact=new Set(['date','time','rating','screen','seat','terminal','cabin','direction','show_type','transport_type','departure_at','arrival_at','departure_zone','arrival_zone'])
const labels:Record<string,string>={transport_type:'交通方式',departure_at:'出发时间',arrival_at:'到达时间',departure_zone:'出发时区',arrival_zone:'到达时区'}
const fields=computed(()=>{
 const order=new Map<string,string>()
 for(const [key,label] of entryFields[props.entry.kind]||[])order.set(key,label)
 // Older source-authored cards may use another known field on the same kind.
 // Keep those visible too; internal place UUIDs are never printed as prose.
 const fallback:Record<string,string>={date:'日期',time:'时间',review:'感受',description:'备注'}
 for(const [key,label] of Object.values(entryFields).flat())if(!order.has(key))order.set(key,fallback[key]||label)
 return [...order].flatMap(([key,label])=>{
  const value=props.entry.fields[key]
  return typeof value==='string'&&value.trim()?[{key,label:labels[key]||label,value,
    note:notes.has(key),wide:!compact.has(key)||value.length>48,display:(key==='departure_at'||key==='arrival_at')?value.replace(/^(\d{4}-\d{2}-\d{2})T/,'$1 '):value}]:[]
 })
})
const details=computed(()=>fields.value.filter(f=>!f.note))
const reflections=computed(()=>fields.value.filter(f=>f.note))
</script>

<template>
  <article class="life-entry-card" :data-entry-kind="entry.kind">
    <header class="entry-heading">
      <div class="entry-kicker">
        <!-- Original elementary SVG geometry, no external icon library/artwork. -->
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <template v-if="entry.kind==='l'"><path d="M12 21s7-7 7-12a7 7 0 0 0-14 0c0 5 7 12 7 12Z"/><circle cx="12" cy="9" r="2.5"/></template>
          <template v-else-if="entry.kind==='f'"><circle cx="13" cy="12" r="6"/><path d="M3 3v6h3V3M4.5 3v18M21 3v18M21 3c-3 3-3 8 0 8"/></template>
          <template v-else-if="entry.kind==='m'"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/></template>
          <template v-else-if="entry.kind==='s'"><path d="M4 4h16v16H4zM4 4l6 5-6 5M20 4l-6 5 6 5M8 20v-3h8v3"/><circle cx="12" cy="11" r="1"/></template>
          <template v-else-if="entry.kind==='g'"><path d="M4 10h16v11H4zM3 7h18v3H3zM12 7v14M12 7C5 7 5 1 9 3l3 4ZM12 7c7 0 7-6 3-4l-3 4Z"/></template>
          <template v-else><rect x="5" y="3" width="14" height="15" rx="3"/><path d="M5 11h14M12 3v8M8 18l-2 3M16 18l2 3"/><circle cx="9" cy="14.5" r=".5"/><circle cx="15" cy="14.5" r=".5"/></template>
        </svg>
        <span>{{entryNames[entry.kind]}}记录</span>
      </div>
      <component :is="heading" class="entry-title">{{entry.name}}</component>
      <slot name="actions"/>
    </header>
    <div v-if="entry.media_ids.length&&$slots.media" class="entry-visuals"><slot name="media"/><span class="entry-photo-count">{{entry.media_ids.length}} 张关联照片</span></div>
    <dl v-if="details.length" class="entry-details">
      <div v-for="field in details" :key="field.key" class="entry-detail" :class="{'entry-detail-wide':field.wide}"><dt>{{field.label}}</dt><dd>{{field.display}}</dd></div>
    </dl>
    <section v-for="field in reflections" :key="field.key" class="entry-reflection"><h4>{{field.label}}</h4><p>{{field.value}}</p></section>
    <footer v-if="$slots.footer" class="entry-footer"><slot name="footer"/></footer>
  </article>
</template>

<style scoped>
.life-entry-card{min-width:0;margin:18px 0;padding:clamp(16px,3vw,26px);border:1px solid var(--line);border-radius:14px;background:var(--paper);color:var(--ink);box-shadow:0 3px 14px color-mix(in srgb,var(--ink) 5%,transparent);overflow-wrap:anywhere}
.entry-heading{display:grid;gap:10px}.entry-kicker{display:flex;align-items:center;gap:9px;color:var(--accent);font-size:12px;font-weight:650;letter-spacing:.1em}.entry-kicker svg{flex-shrink:0}.entry-title{margin:0!important;color:var(--ink);font-size:clamp(20px,2.6vw,28px);font-weight:650;line-height:1.35;letter-spacing:-.025em;text-wrap:pretty}
.entry-details{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(125px,100%),1fr));gap:15px 22px;margin:20px 0 0;padding:0}.entry-detail{min-width:0}.entry-detail-wide{grid-column:1/-1}.entry-details dt,.entry-reflection h4{margin:0 0 5px;color:var(--muted);font-size:12px;font-weight:500;line-height:1.5}.entry-details dd{margin:0;white-space:pre-line;font-size:14px;line-height:1.7}
.entry-reflection{margin-top:18px;border-top:1px solid var(--line);padding-top:15px}.entry-reflection p{margin:0;white-space:pre-line;font-size:14px;line-height:1.85;color:var(--ink)}.entry-reflection h4{letter-spacing:.06em}
.entry-visuals{margin-top:18px;min-width:0}.entry-visuals :deep(.entry-thumbnails){display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.entry-visuals :deep(img){display:block;max-width:100%;width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:8px}.entry-photo-count{display:block;margin-top:7px;font-size:11px;color:var(--muted)}.entry-footer{margin-top:20px;padding-top:12px;border-top:1px solid var(--line);font-size:12px}.entry-footer :deep(a){color:var(--accent);text-decoration-thickness:1px;text-underline-offset:3px}
@media(max-width:600px){.life-entry-card{margin:14px 0;padding:16px}.entry-details{gap:13px 16px}.entry-title{font-size:21px}.entry-visuals :deep(.entry-thumbnails){grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
