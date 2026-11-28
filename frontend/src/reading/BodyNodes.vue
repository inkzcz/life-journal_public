<script setup lang="ts">
import {entrySummary,entryIcons} from './entrySummary'
import type {Entry} from '../writing/entries'
import EntryCard from '../writing/EntryCard.vue'
import InlineMedia from './InlineMedia.vue'
import {type MediaBlock,type BodyNode} from '../writing/body'
export type RenderedBodyNode=BodyNode&{html?:string;children?:RenderedBodyNode[]}
defineProps<{nodes:RenderedBodyNode[];photos:MediaBlock[];plain?:boolean}>()
const emit=defineEmits<{open:[entry:Entry,event:MouseEvent]}>()
</script>
<template><template v-for="(node,index) in nodes" :key="index"><button v-if="node.entry&&plain" type="button" class="entry-inline" aria-haspopup="dialog" @click="emit('open',node.entry,$event)"><span aria-hidden="true">{{entryIcons[node.entry.kind]}}</span> {{entrySummary(node.entry)}}</button><EntryCard v-else-if="node.entry" tabindex="-1" :id="'entry-'+node.entry.id" :entry="node.entry"><template #media><InlineMedia :images="node.entry.media_ids.map(id=>({id,alt:node.entry!.name,caption:'',width:960,align:'center' as const}))" :photos="photos"/></template></EntryCard><InlineMedia v-else-if="node.media||node.gallery" :images="node.gallery||(node.media?[node.media]:[])" :photos="photos"/><component :is="node.tag" v-else-if="node.tag" :start="node.start"><BodyNodes :nodes="node.children||[]" :photos="photos" :plain="plain" @open="(entry,event)=>emit('open',entry,event)"/></component><div v-else v-html="node.html"></div></template></template>

<style scoped>.entry-inline{display:block;max-width:100%;margin:8px 0;padding:6px 10px;text-align:left;white-space:normal;overflow-wrap:anywhere;font:inherit;color:inherit;background:var(--surface,transparent);border:1px solid var(--line,var(--ui-line));border-radius:var(--ui-radius,6px)}</style>
