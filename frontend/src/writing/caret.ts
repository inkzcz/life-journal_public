export type Caret={left:number;top:number;bottom:number}
// A detached-looking mirror measures textarea wrapping without resizing the editor.
export function textareaCaret(el:HTMLTextAreaElement):Caret{
 const box=el.getBoundingClientRect(),style=getComputedStyle(el),mirror=document.createElement('div')
 for(const key of ['font','lineHeight','letterSpacing','padding','border','boxSizing','wordSpacing','tabSize'] as const)mirror.style[key]=style[key]
 Object.assign(mirror.style,{position:'fixed',left:box.left+'px',top:box.top+'px',width:box.width+'px',height:box.height+'px',whiteSpace:'pre-wrap',overflowWrap:'break-word',visibility:'hidden',pointerEvents:'none',overflow:'hidden'})
 mirror.textContent=el.value.slice(0,el.selectionStart);const span=document.createElement('span');span.textContent='\u200b';mirror.append(span);document.body.append(mirror)
 const r=span.getBoundingClientRect(),line=parseFloat(style.lineHeight)||20;mirror.remove()
 return {left:r.left-el.scrollLeft,top:r.top-el.scrollTop,bottom:r.top-el.scrollTop+line}
}
export function popupPosition(anchor:Caret,width:number,height:number){
 const v=window.visualViewport,left=v?.offsetLeft||0,top=v?.offsetTop||0,w=v?.width||innerWidth,h=v?.height||innerHeight,pad=8
 return {left:Math.max(left+pad,Math.min(anchor.left,left+w-width-pad)),top:Math.max(top+pad,Math.min(anchor.bottom+6+height>top+h-pad?anchor.top-height-6:anchor.bottom+6,top+h-height-pad))}
}
export function suggestionMatch(context:string){
 // A CJK sentence may precede a typed kind; a bare @ inside a word stays inert.
 const m=/(?:^|[^\p{L}\p{N}_@]|(?<=[\u3400-\u9fff])(?=@[lfshtcp]))(@([lfshtcp]?)(?:[\t ]+([^@\n{}]*)|\[([^\]\n{}]*)|([^\s@\[\]{}\n]*))?)$/u.exec(context)
 if(!m||/\S*(?:https?:\/\/|www\.|mailto:)[^\s]*$/i.test(context)||(context.match(/`/g)||[]).length%2===1)return null
 if(m)m[3]=m[3]??m[4]??m[5]??''
 return m
}

// Only a complete command at a text boundary is offered as a new card.
// Existing place tokens, links, code and email addresses keep their meaning.
export function cardCommandMatch(context:string){
 const m=/(?:^|[\s，。！？；：、（）])(@([lfmsgt]?))$/u.exec(context)
 if(!m||/(?:https?:\/\/|www\.|mailto:)[^\s]*$/i.test(context))return null
 const prefix=context.slice(0,context.length-m[1]!.length)
 let codeDelimiter=0;for(const run of prefix.matchAll(/(?<!\\)`+/g)){if(!codeDelimiter)codeDelimiter=run[0].length;else if(codeDelimiter===run[0].length)codeDelimiter=0}
 const inline=prefix.replace(/^\s*[-+*]\s+/,'')
 if(codeDelimiter||prefix.lastIndexOf('<')>prefix.lastIndexOf('>')||(inline.match(/(?<!\\)\*\*/g)||[]).length%2||(inline.match(/(?<!\\)__/g)||[]).length%2||(inline.match(/(?<![\\*])\*(?!\*)/g)||[]).length%2||/[\[\]{}<>\\]/.test(prefix.slice(prefix.lastIndexOf(' ')+1))||/!?(?:\[[^\]]*|\[[^\]]*\]\([^)]*)$/.test(prefix))return null
 return {raw:m[1]!,kind:m[2]||undefined}
}
