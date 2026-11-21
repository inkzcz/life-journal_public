import type {EditorView} from '@tiptap/pm/view'
// Prefix text blocks instead of replacing a selection. Selected private-media
// atoms and all authored text remain intact; ProseMirror maps the selection.
export function indentVisualText(view:EditorView,shift=false){
 const {from,to,$from,empty}=view.state.selection,positions:number[]=[]
 if(empty&&$from.parent.isTextblock)positions.push($from.start())
 else view.state.doc.nodesBetween(from,to,(node,pos)=>{if(node.isTextblock){positions.push(pos+1);return false}})
 const tr=view.state.tr
 for(const pos of positions.reverse()){
  if(!shift)tr.insertText('  ',pos)
  else{const text=view.state.doc.textBetween(pos,Math.min(pos+2,view.state.doc.content.size),'');const count=/^ {1,2}/.exec(text)?.[0].length||0;if(count)tr.delete(pos,pos+count)}
 }
 if(tr.docChanged)view.dispatch(tr)
}
