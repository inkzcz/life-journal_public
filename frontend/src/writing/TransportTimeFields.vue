<script setup lang="ts">
import {computed,reactive,ref,watch} from 'vue'
import type {Entry} from './entries'
import TimeZoneSelect from './TimeZoneSelect.vue'
import {possibleTimes,readStamp,stampMatchesZone,travelDuration,validZone,offsetLabel,type ZonedCandidate} from './zonedTime'
const props=defineProps<{value:Entry;siteZone:string;disabled?:boolean;recordDate?:string}>(),emit=defineEmits<{(e:'validity',valid:boolean):void}>()
type Prefix='departure'|'arrival'
type Row={date:string;time:string;zone:string;choice:string;choices:ZonedCandidate[];error:string;warning:string;edited:boolean}
function initial(prefix:Prefix):Row{const raw=props.value.fields[prefix+'_at']||'',stamp=readStamp(raw),zone=props.value.fields.independent_zones==='false'?props.siteZone:props.value.fields[prefix+'_zone']||props.siteZone;const choices=stamp&&validZone(zone)?possibleTimes(stamp.date,stamp.time,zone):[];return {date:stamp?.date||(!props.value.fields.departure_at&&!props.value.fields.arrival_at?props.recordDate||'':''),time:stamp?.time||'',zone,choice:stamp?String(choices.find(c=>c.offsetMinutes===stamp.offsetMinutes)?.epoch??''):'',choices,error:'',edited:false,warning:raw&&!stamp?'历史时间无法自动解析，原值保持；修改时请重新选择。':raw&&zone&&!stampMatchesZone(raw,zone)?'历史UTC偏移与该IANA时区不一致，原值保持；修改后请明确选择有效时间。':''}}
const rows=reactive({departure:initial('departure'),arrival:initial('arrival')})
const independent=ref(props.value.fields.independent_zones==='true'||props.value.fields.independent_zones!=='false'&&!!(props.value.fields.departure_zone||props.value.fields.arrival_zone))
const requested=ref(independent.value),policy=ref('')
let arrivalDateEdited=!!props.value.fields.arrival_at
watch(()=>props.recordDate,date=>{if(!props.value.fields.departure_at&&!rows.departure.edited){rows.departure.date=date||'';if(!arrivalDateEdited)rows.arrival.date=date||''}})
watch(()=>props.siteZone,zone=>{if(!independent.value)for(const prefix of ['departure','arrival'] as Prefix[])rows[prefix].zone=zone})
function dateChanged(prefix:Prefix){if(prefix==='arrival')arrivalDateEdited=true;changed(prefix);if(prefix==='departure'&&!arrivalDateEdited){rows.arrival.date=rows.departure.date;if(rows.arrival.time)changed('arrival')}}
function applyZones(){
 if(!policy.value)return
 for(const prefix of ['departure','arrival'] as Prefix[]){if(props.value.fields[prefix+'_at']&&!readStamp(props.value.fields[prefix+'_at']!)){rows[prefix].error='历史时间无法转换，请先明确修正日期和时间';return}}
 const target=requested.value
 if(!target&&!validZone(props.siteZone))return
 for(const prefix of ['departure','arrival'] as Prefix[]){
  const row=rows[prefix],zone=target?row.zone||props.siteZone:props.siteZone,stamp=readStamp(props.value.fields[prefix+'_at']||'')
  row.zone=zone
  if(policy.value==='instant'&&stamp&&validZone(zone)){
   const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(stamp.epoch).map(p=>[p.type,p.value]))
   row.date=parts.year+'-'+parts.month+'-'+parts.day;row.time=parts.hour+':'+parts.minute
   const choice=possibleTimes(row.date,row.time,zone).find(c=>Math.abs(c.epoch-stamp.epoch)<60000)
   if(choice){const fraction=(props.value.fields[prefix+'_at']||'').match(/T\d{2}:\d{2}(:\d{2}(?:\.\d+)?)?/i)?.[1]||'';commit(prefix,{...choice,iso:choice.iso.slice(0,16)+fraction+choice.iso.slice(16)})}
  }else if(policy.value==='local'&&(row.time||props.value.fields[prefix+'_at'])){
   const seconds=(props.value.fields[prefix+'_at']||'').match(/[Tt ]\d{2}:\d{2}(:\d{2}(?:\.\d+)?)?/)?.[1]||''
   changed(prefix)
   if(seconds&&!row.error){const raw=props.value.fields[prefix+'_at']||'';props.value.fields[prefix+'_at']=raw.slice(0,16)+seconds+raw.slice(16)}
  }
 }
 independent.value=target;props.value.fields.independent_zones=String(target);policy.value=''
}
const orderError=computed(()=>{const a=readStamp(props.value.fields.departure_at||''),b=readStamp(props.value.fields.arrival_at||'');return a&&b&&b.epoch<a.epoch?'到达的实际时间早于出发，请核对日期和时区。':''})
const valid=computed(()=>requested.value===independent.value&&!rows.departure.error&&!rows.arrival.error&&!orderError.value)
watch(valid,value=>emit('validity',value),{immediate:true})
const duration=computed(()=>valid.value?travelDuration(props.value.fields.departure_at||'',props.value.fields.arrival_at||''):'')
function commit(prefix:Prefix,candidate:ZonedCandidate){const row=rows[prefix];row.error='';row.warning='';props.value.fields.independent_zones=String(independent.value);props.value.fields[prefix+'_at']=candidate.iso;props.value.fields[prefix+'_zone']=row.zone}
function changed(prefix:Prefix){const row=rows[prefix];row.edited=true;row.warning='';row.choice='';row.choices=[];if(!row.date&&!row.time){if(row.zone&&!validZone(row.zone)){row.error='请选择有效IANA时区';return}row.error='';props.value.fields[prefix+'_at']='';props.value.fields[prefix+'_zone']=row.zone;return}if(!row.date||!row.time){row.error='请补全日期和时间，或同时清空';return}if(!validZone(row.zone)){row.error='请选择有效IANA时区';return}row.choices=possibleTimes(row.date,row.time,row.zone);if(!row.choices.length){row.error='所选当地时间不存在或日期无效，请检查夏令时切换';return}if(row.choices.length>1){row.error='当地时间重复，请明确选择UTC偏移';return}row.choice=String(row.choices[0]!.epoch);commit(prefix,row.choices[0]!)}
function choose(prefix:Prefix){const row=rows[prefix],selected=row.choices.find(c=>String(c.epoch)===row.choice);if(selected)commit(prefix,selected)}
function sameZone(){rows.arrival.zone=rows.departure.zone;changed('arrival')}
</script>
<template><section class="transport-time-fields"><label><input v-model="requested" type="checkbox" aria-label="独立时区" :disabled="disabled"/>独立时区</label><div v-if="requested!==independent" class="zone-policy"><label>切换方式<select v-model="policy" aria-label="时区切换方式" :disabled="disabled"><option value="" disabled>请明确选择</option><option value="local">保留当地日期和时间（实际时刻可能改变）</option><option value="instant">保留绝对时刻（转换当地日期和时间）</option></select></label><button type="button" :disabled="disabled||!policy||(!requested&&!siteZone)" @click="applyZones">应用时区切换</button></div><p v-if="!independent" class="muted">使用站点时区 {{siteZone}}</p><fieldset v-for="prefix in (['departure','arrival'] as const)" :key="prefix" :disabled="disabled"><legend>{{prefix==='departure'?'出发信息':'到达信息'}}</legend><div class="time-pair"><label>{{prefix==='departure'?'出发日期':'到达日期'}}<input :aria-label="prefix==='departure'?'出发日期':'到达日期'" v-model="rows[prefix].date" type="date" @change="dateChanged(prefix)"/></label><label>{{prefix==='departure'?'出发时间':'到达时间'}}<input :aria-label="prefix==='departure'?'出发时间':'到达时间'" v-model="rows[prefix].time" type="time" @change="changed(prefix)"/></label></div><TimeZoneSelect v-if="independent" v-model="rows[prefix].zone" :label="prefix==='departure'?'出发地时区':'到达地时区'" :disabled="disabled" @update:modelValue="changed(prefix)"/><label v-if="rows[prefix].choices.length>1">重复时间偏移<select v-model="rows[prefix].choice" :aria-label="prefix==='departure'?'出发重复时间偏移':'到达重复时间偏移'" @change="choose(prefix)"><option value="" disabled>请明确选择</option><option v-for="c in rows[prefix].choices" :key="c.epoch" :value="String(c.epoch)">UTC{{offsetLabel(c.offsetMinutes)}}</option></select></label><p v-if="rows[prefix].warning" role="status">{{rows[prefix].warning}}</p><p v-if="rows[prefix].error" role="alert">{{rows[prefix].error}}</p></fieldset><button v-if="independent" type="button" class="quiet" :disabled="disabled||!rows.departure.zone" @click="sameZone">将出发时区应用到到达</button><p v-if="duration" class="journey-duration">实际耗时 {{duration}}</p><p v-if="orderError" role="alert">{{orderError}}</p><p v-if="!siteZone" class="muted">站点时区尚未读取，请明确选择时区；不会使用浏览器时区代替。</p></section></template>
<style scoped>.transport-time-fields{min-width:0;container-type:inline-size}.transport-time-fields fieldset{min-width:0;border:1px solid var(--line);border-radius:12px;padding:12px;margin-block:12px}.time-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}label{display:block;min-width:0}input[type=checkbox]{width:auto}input,select{width:100%;max-width:100%;box-sizing:border-box}.journey-duration{font-weight:600;color:var(--accent)}[role=alert]{color:var(--danger,var(--ink));overflow-wrap:anywhere}@container(max-width:460px){.time-pair{grid-template-columns:minmax(0,1fr)}}</style>
