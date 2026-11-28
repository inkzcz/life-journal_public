import {entryNames,type Entry} from '../writing/entries'
export const entryIcons={l:'⌖',f:'♨',m:'▣',s:'♫',g:'◇',t:'➜'}
export function entrySummary(entry:Entry){const route=entry.kind==='t'?[entry.fields.departure,entry.fields.destination].filter(Boolean).join(' → '):'';const name=entry.kind==='t'?entry.fields.service_number||entry.name:entry.name;return `${entryNames[entry.kind]} · ${name}${route?' · '+route:''}`}
