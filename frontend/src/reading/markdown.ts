import type {TokensList} from 'marked'
import { renderMarkdown } from '../markdown'

export type Heading = { id: string; text: string; level: number }
// Sanitize first. IDs come only from the controlled namespace and ordinal,
// never from authored HTML or a second Markdown parser. Stable for this revision.
export function articleMarkdown(source: string, namespace: string, offset=0,links?:TokensList['links']) {
  const template = document.createElement('template')
  template.innerHTML = renderMarkdown(source,links)
  const prefix = 'lj-' + namespace.replace(/[^a-zA-Z0-9_-]/g, '-')
  // Authored HTML cannot forge the reserved reader marker/anchor namespace.
  template.content.querySelectorAll<HTMLElement>('[data-reading-heading],[id],[name]').forEach(element=>{
    element.removeAttribute('data-reading-heading')
    for(const attr of ['id','name'])if(element.getAttribute(attr)?.startsWith('lj-'))element.removeAttribute(attr)
  })
  const headings: Heading[] = []
  template.content.querySelectorAll<HTMLElement>('h2,h3,h4').forEach((element, index) => {
    // Preserve pre-existing safe authored links while owning the TOC ID.
    if(element.id){const alias=document.createElement('span');alias.id=element.id;alias.className='legacy-heading-anchor';alias.setAttribute('aria-hidden','true');element.before(alias)}
    const id = `${prefix}-heading-${offset + index + 1}`
    element.id = id; element.dataset.readingHeading = ''; element.tabIndex = -1
    headings.push({ id, text: element.textContent?.trim() || '未命名章节', level: Number(element.tagName[1]) })
  })
  return { html: template.innerHTML, headings }
}
