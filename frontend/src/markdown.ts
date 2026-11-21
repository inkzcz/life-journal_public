import { marked,type TokensList } from 'marked'
import {decoratePlaces} from './writing/places'
import DOMPurify from 'dompurify'

export function renderMarkdown(source: string,links?:TokensList['links']): string {
  // Inline reference resolution needs the whole document's definitions, even
  // when lists/private images are rendered as separate Vue fragments.
  let html:string
  if(links&&Object.keys(links).length){
    const lexer=new marked.Lexer(marked.defaults)
    lexer.tokens.links=Object.assign(Object.create(null),links)
    html=marked.parser(lexer.lex(source),marked.defaults)
  }else html=marked.parse(source,{async:false})
  const clean=DOMPurify.sanitize(html, {
    // Remote images could disclose reading activity; photos use the authenticated gallery.
    FORBID_TAGS: ['img', 'iframe', 'style', 'form', 'input'],
    FORBID_ATTR: ['style', 'target'],
  })
  const template=document.createElement('template');template.innerHTML=clean;decoratePlaces(template);return template.innerHTML
}
