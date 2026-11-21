<script setup lang="ts">
import {loadTypography} from '../presentation/typography'
import { computed,onMounted,provide } from 'vue'
import { bodyTree,compactBody,type MediaBlock,type BodyNode } from '../writing/body'
import BodyNodes,{type RenderedBodyNode} from './BodyNodes.vue'
import { articleMarkdown } from './markdown'
import {readingPreview,type PreviewImage} from './mediaPreview'
onMounted(()=>void loadTypography())
const props=defineProps<{source:string;namespace:string;format?:number;previewMedia?:PreviewImage[]}>()
provide(readingPreview,computed(()=>props.previewMedia))
const rendered=computed(()=>{
 const tree=bodyTree(props.source,props.format||1)
 let offset=0
 function render(nodes:BodyNode[]):RenderedBodyNode[]{return nodes.map(node=>{
  if(node.children)return {...node,children:render(node.children)}
  if(node.entry||node.media||node.gallery)return node
  const result=articleMarkdown(node.source||'',props.namespace,offset,tree.links);offset+=result.headings.length
  return {...node,html:result.html}
 })}
 return render(compactBody(tree))
})
const photos=computed(()=>{const collect=(nodes:BodyNode[]):MediaBlock[]=>nodes.flatMap(n=>n.entry?n.entry.media_ids.map(id=>({id,alt:n.entry!.name,caption:'',width:960,align:'center' as const})):n.gallery|| (n.media?[n.media]:n.children?collect(n.children):[]));return collect(rendered.value)})
</script>
<template><div class="blog-prose article-body"><BodyNodes :nodes="rendered" :photos="photos"/></div></template>
