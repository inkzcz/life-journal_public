/** An AI result is a proposal, never an authority over newer editor contents. */
export type AICapture={id:string;body:string;selection:string;mode:'source'|'visual';format:number}
export type AIApply='insert'|'selection'|'replace'
export type AIEditor={captureAI:()=>AICapture|null;applyAI:(id:string,text:string,action:AIApply)=>boolean;undoAI:()=>boolean}
export function sourcePatch(body:string,from:number,to:number,text:string,action:AIApply){
 if(!Number.isInteger(from)||!Number.isInteger(to)||from<0||to<from||to>body.length)throw Error('原选区已失效')
 const split=(n:number)=>n>0&&n<body.length&&/[\uD800-\uDBFF]/.test(body[n-1])&&/[\uDC00-\uDFFF]/.test(body[n])
 if(split(from)||split(to))throw Error('选区不能拆分Unicode字符')
 const start=action==='replace'?0:action==='insert'?to:from,end=action==='replace'?body.length:to
 const value=body.slice(0,start)+text+body.slice(end)
 if(value.length>300000)throw Error('应用后正文超过300000字符')
 return {value,caret:start+text.length}
}
