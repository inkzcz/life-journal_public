import type {InjectionKey,ComputedRef} from 'vue'
import type {Entry} from './entries'
export const entryTransferKey:InjectionKey<(entry:Entry,operation:'copy'|'move')=>Promise<void>>=Symbol('entry-transfer')

// A NodeView's local form is not yet part of the ProseMirror document.
// Track the component lifetime rather than the card UUID (NodeViews can be replaced).
export const entryDraftStateKey:InjectionKey<(owner:symbol,pending:boolean)=>void>=Symbol('entry-draft-state')

export const entryRecordDateKey:InjectionKey<ComputedRef<string|undefined>>=Symbol('entry-record-date')
export const entryDraftGuardKey:InjectionKey<(owner?:symbol)=>boolean>=Symbol('entry-draft-guard')
