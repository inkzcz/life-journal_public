<script setup lang="ts">
import {ref,watch,inject,onMounted,onBeforeUnmount} from 'vue'
import {NodeViewWrapper,nodeViewProps} from '@tiptap/vue-3'
import {cardBounds,duplicateCard,moveCard,deleteCard} from './entryDocument'
import {entryTransferKey,entryDraftStateKey} from './entryTransfer'
import {validEntry,type Entry} from './entries'
import EntryForm from './EntryForm.vue'
import EntryCard from './EntryCard.vue'
import EntryCardActions from './cards/EntryCardActions.vue'
import {confirmAction} from '../ui/confirm'
import {computed} from 'vue'
import PrivatePreview from '../admin/PrivatePreview.vue'
const props=defineProps(nodeViewProps),opened=ref(false),error=ref('')
const transfer=inject(entryTransferKey,undefined)
const reportDraft=inject(entryDraftStateKey,undefined),draftOwner=Symbol('card-form')
function localReady(){if(opened.value&&(!timeValid.value||JSON.stringify(draft.value)!==JSON.stringify(props.node.attrs.value))){error.value='请先保存或取消当前卡片编辑';return false}return true}
function transferCard(operation:'copy'|'move'){if(localReady())void transfer?.(props.node.attrs.value,operation)}
function duplicate(){if(localReady())duplicateCard(props.editor,props.node.attrs.value.id)}
const timeValid=ref(true)
const draft=ref<Entry>(JSON.parse(JSON.stringify(props.node.attrs.value)))
watch(()=>opened.value&&(!timeValid.value||JSON.stringify(draft.value)!==JSON.stringify(props.node.attrs.value)),value=>reportDraft?.(draftOwner,value),{immediate:true,flush:'sync'})
onBeforeUnmount(()=>reportDraft?.(draftOwner,false))
watch(opened,()=>{draft.value=JSON.parse(JSON.stringify(props.node.attrs.value));error.value=''})
function save(){if(!props.editor.isEditable)return;if(!timeValid.value){error.value='请先处理时间与时区提示';return;}if(!validEntry(draft.value)){error.value='请填写名称并核对字段';return}if(draft.value.kind!==props.node.attrs.value.kind){error.value='修改已有卡片的类型请新增另一张卡片';return}props.updateAttributes({value:JSON.parse(JSON.stringify(draft.value))});opened.value=false}

const positionRevision=ref(0)
function refreshPosition(){positionRevision.value++}
onMounted(()=>props.editor.on('transaction',refreshPosition));onBeforeUnmount(()=>props.editor.off('transaction',refreshPosition))
const bounds=computed(()=>{void positionRevision.value;return cardBounds(props.editor,props.node.attrs.value.id)})
function reorder(direction:'up'|'down'){if(localReady())moveCard(props.editor,props.node.attrs.value.id,direction)}
async function action(key:string){if(!localReady())return;if(key==='edit'){opened.value=!opened.value}else if(key==='duplicate')duplicate();else if(key==='copy'||key==='move')transferCard(key);else if(key==='up'||key==='down')reorder(key);else if(key==='delete'&&await confirmAction('仅删除正文中的这张卡片？关联媒体和历史记录将保留。'))deleteCard(props.editor,props.node.attrs.value.id)}
</script>
<template><NodeViewWrapper class="entry-card" contenteditable="false" :id="'entry-'+node.attrs.value.id"><EntryCard :entry="node.attrs.value"><template #actions><EntryCardActions v-if="editor.isEditable" :transfer="!!transfer" :can-up="bounds.up" :can-down="bounds.down" @action="action"/></template><template #media><div class="entry-thumbnails"><PrivatePreview v-for="id in node.attrs.value.media_ids" :key="id" :id="id" :alt="node.attrs.value.name"/></div></template></EntryCard><form v-if="opened" @submit.stop.prevent="save" @mousedown.stop @click.stop><EntryForm :value="draft" :disabled="!editor.isEditable" @validity="timeValid=$event"/><p role="status">{{error}}</p><div class="entry-card-actions"><button type="submit" :disabled="!editor.isEditable">保存卡片</button><button type="button" class="quiet" :disabled="!editor.isEditable" @click="opened=false">取消</button></div></form></NodeViewWrapper></template>
<style scoped>.entry-card{margin:16px 0;min-width:0}.entry-card>form{border:1px solid var(--line);padding:16px;border-radius:var(--ui-radius);background:var(--paper);min-width:0}.entry-edit{justify-self:start;font-size:12px;padding:5px 10px}.entry-card-actions{position:sticky;bottom:0;background:var(--paper);padding:10px 0 max(10px,env(safe-area-inset-bottom));display:flex;flex-wrap:wrap;gap:8px}</style>
