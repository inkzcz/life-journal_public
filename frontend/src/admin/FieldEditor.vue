<script setup lang="ts">
import {newId} from '../ids'
import { kinds, newField, type Field } from './types'
import ValueInput from './ValueInput.vue'
function withGroup(f:Field):Field & {group?:string}{return f}
const props=defineProps<{fields:Field[];disabled:boolean}>()
function move(index:number,direction:number){const next=index+direction;if(next<0||next>=props.fields.length)return;const item=props.fields.splice(index,1)[0]!;props.fields.splice(next,0,item)}
function reset(field:Field){field.rules={};field.searchable=false;field.has_default=false;field.default_value=null}
function addOption(field:Field){if(!field.rules.options)field.rules.options=[];field.rules.options.push({id:newId(),label:'',active:true})}
</script>
<template>
  <section aria-label="字段配置">
    <h3>自定义字段</h3><p class="muted">已有字段可改名、调整顺序或停用；停用会保留历史值。新增必填只影响新版本。</p>
    <div v-for="(f,index) in fields" :key="f.id||index" class="field-config">
      <div class="actions"><strong>字段 {{index+1}}</strong><button type="button" class="quiet" :disabled="disabled||index===0" @click="move(index,-1)">上移</button><button type="button" class="quiet" :disabled="disabled||index===fields.length-1" @click="move(index,1)">下移</button><button v-if="!f.id" type="button" class="quiet" :disabled="disabled" @click="fields.splice(index,1)">移除未保存字段</button></div>
      <div class="editor-meta"><label>字段名称<input v-model="f.name" required maxlength="100" :disabled="disabled" /></label>
      <label>字段种类<select aria-label="字段种类" v-model="f.kind" :disabled="disabled||!!f.id" @change="reset(f)"><option v-for="(label,key) in kinds" :key="key" :value="key">{{label}}</option></select></label></div>
      <label>字段说明<input v-model="f.description" maxlength="2000" :disabled="disabled" /></label>
      <label v-if="['short_text','long_text','markdown'].includes(f.kind)" class="checks"><input v-model="f.searchable" type="checkbox" :disabled="disabled" /> 允许在生活归档中搜索此字段（保存为新字段版本）</label><div class="checks"><label><input v-model="f.required" type="checkbox" :disabled="disabled" /> 必填（发布时）</label><label><input v-model="f.active" type="checkbox" :disabled="disabled" /> 启用字段</label></div>
      <div v-if="['short_text','long_text','markdown'].includes(f.kind)" class="editor-meta"><label>最少字符<input v-model.number="f.rules.min_length" type="number" min="0" max="300000" :disabled="disabled" /></label><label>最多字符<input v-model.number="f.rules.max_length" type="number" min="1" max="300000" :disabled="disabled" /></label></div>
      <div v-if="['integer','decimal'].includes(f.kind)" class="editor-meta"><label>最小数值<input v-model="f.rules.min_value" type="number" :step="f.kind==='integer'?'1':'any'" :disabled="disabled" /></label><label>最大数值<input v-model="f.rules.max_value" type="number" :step="f.kind==='integer'?'1':'any'" :disabled="disabled" /></label></div>
      <div v-if="f.kind==='date'" class="editor-meta"><label>最早日期<input v-model="f.rules.min_date" type="date" :disabled="disabled" /></label><label>最晚日期<input v-model="f.rules.max_date" type="date" :disabled="disabled" /></label></div>
      <template v-if="['select','multiselect'].includes(f.kind)">
        <div v-for="o in f.rules.options||[]" :key="o.id" class="option-row"><label>选项名称<input v-model="o.label" required maxlength="100" :disabled="disabled" /></label><label><input v-model="o.active" type="checkbox" :disabled="disabled" /> 启用选项</label></div>
        <button type="button" class="quiet" :disabled="disabled||(f.rules.options?.length||0)>=50" @click="addOption(f)">添加选项</button>
        <label v-if="f.kind==='multiselect'">最多可选数量<input v-model.number="f.rules.max_items" type="number" min="1" max="50" :disabled="disabled" /></label>
      </template>
      <slot name="extra" :field="withGroup(f)"></slot>
      <label class="checks"><input v-model="f.has_default" type="checkbox" :disabled="disabled" /> 为新记录设置默认值</label>
      <ValueInput v-if="f.has_default" v-model="f.default_value" :field="f" label="默认值" :disabled="disabled" />
    </div>
    <button type="button" class="quiet" :disabled="disabled||fields.length>=50" @click="fields.push(newField())">添加字段</button>
  </section>
</template>
