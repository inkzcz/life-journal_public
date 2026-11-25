<script setup lang="ts">
import {ref,watch,inject} from 'vue'
import {NodeViewWrapper,nodeViewProps} from '@tiptap/vue-3'
import {newId} from '../ids'
import {entryTransferKey} from './entryTransfer'
import {validEntry,type Entry} from './entries'
import EntryForm from './EntryForm.vue'
import EntryCard from './EntryCard.vue'
import PrivatePreview from '../admin/PrivatePreview.vue'
const props=defineProps(nodeViewProps),opened=ref(false),error=ref('')
const transfer=inject(entryTransferKey,undefined)
function localReady(){if(opened.value&&JSON.stringify(draft.value)!==JSON.stringify(props.node.attrs.value)){error.value='请先保存或取消当前卡片编辑';return false}return true}
function transferCard(operation:'copy'|'move'){if(localReady())void transfer?.(props.node.attrs.value,operation)}
function duplicate(){if(!props.editor.isEditable||!localReady())return;const at=props.getPos();if(typeof at!=='number')return;const value=JSON.parse(JSON.stringify(props.node.attrs.value));value.id=newId();props.editor.chain().focus().insertContentAt(at+props.node.nodeSize,{type:props.node.type.name,attrs:{value}}).run()}
const timeValid=ref(true)
const draft=ref<Entry>(JSON.parse(JSON.stringify(props.node.attrs.value)))
watch(opened,()=>{draft.value=JSON.parse(JSON.stringify(props.node.attrs.value));error.value=''})
function save(){if(!props.editor.isEditable)return;if(!timeValid.value){error.value='请先处理时间与时区提示';return;}if(!validEntry(draft.value)){error.value='请填写名称并核对字段';return}if(draft.value.kind!==props.node.attrs.value.kind){error.value='修改已有卡片的类型请新增另一张卡片';return}props.updateAttributes({value:JSON.parse(JSON.stringify(draft.value))});opened.value=false}
</script>
<template><NodeViewWrapper class="entry-card" contenteditable="false" :id="'entry-'+node.attrs.value.id"><EntryCard :entry="node.attrs.value"><template #actions><button v-if="editor.isEditable" type="button" class="quiet entry-edit" :aria-expanded="opened" @click="opened=!opened">{{opened?'收起编辑':'编辑卡片'}}</button><button v-if="editor.isEditable" type="button" class="quiet" @click="duplicate">复制卡片</button><button v-if="editor.isEditable&&transfer" type="button" class="quiet" @click="transferCard('copy')">复制到其他文章</button><button v-if="editor.isEditable&&transfer" type="button" class="quiet" @click="transferCard('move')">移动到其他文章</button></template><template #media><div class="entry-thumbnails"><PrivatePreview v-for="id in node.attrs.value.media_ids.slice(0,3)" :key="id" :id="id" :alt="node.attrs.value.name"/></div></template></EntryCard><form v-if="opened" @submit.stop.prevent="save" @mousedown.stop @click.stop><EntryForm :value="draft" :disabled="!editor.isEditable" @validity="timeValid=$event"/><p role="status">{{error}}</p><div class="entry-card-actions"><button type="submit" :disabled="!editor.isEditable">保存卡片</button><button type="button" class="quiet" :disabled="!editor.isEditable" @click="opened=false">取消</button><button type="button" class="quiet" :disabled="!editor.isEditable" @click="deleteNode">移除卡片（保留媒体和历史）</button></div></form></NodeViewWrapper></template>
<style scoped>.entry-card{margin:16px 0;min-width:0}.entry-card>form{border:1px solid var(--line);padding:16px;border-radius:var(--ui-radius);background:var(--paper);min-width:0}.entry-edit{justify-self:start;font-size:12px;padding:5px 10px}.entry-card-actions{position:sticky;bottom:0;background:var(--paper);padding:10px 0 max(10px,env(safe-area-inset-bottom));display:flex;flex-wrap:wrap;gap:8px}</style>
