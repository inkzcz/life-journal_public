<script setup lang="ts">
import EntryCard from '../writing/EntryCard.vue'
import InlineMedia from './InlineMedia.vue'
import {type MediaBlock,type BodyNode} from '../writing/body'
export type RenderedBodyNode=BodyNode&{html?:string;children?:RenderedBodyNode[]}
defineProps<{nodes:RenderedBodyNode[];photos:MediaBlock[]}>()
</script>
<template><template v-for="(node,index) in nodes" :key="index"><EntryCard v-if="node.entry" :id="'entry-'+node.entry.id" :entry="node.entry"><template #media><InlineMedia :images="node.entry.media_ids.map(id=>({id,alt:node.entry!.name,caption:'',width:960,align:'center' as const}))" :photos="photos"/></template></EntryCard><InlineMedia v-else-if="node.media||node.gallery" :images="node.gallery||(node.media?[node.media]:[])" :photos="photos"/><component :is="node.tag" v-else-if="node.tag" :start="node.start"><BodyNodes :nodes="node.children||[]" :photos="photos"/></component><div v-else v-html="node.html"></div></template></template>
