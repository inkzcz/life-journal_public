import type {InjectionKey} from 'vue'
import type {Entry} from './entries'
export const entryTransferKey:InjectionKey<(entry:Entry,operation:'copy'|'move')=>Promise<void>>=Symbol('entry-transfer')
