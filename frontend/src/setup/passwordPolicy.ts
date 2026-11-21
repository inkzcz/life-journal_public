import { reactive } from 'vue'
import { request } from '../api'
const policy=reactive({minimum:8,maximum:1024,common:[] as string[]})
export async function loadPasswordPolicy(){Object.assign(policy,await request('/auth/password-policy'))}
export function passwordError(value:string){const length=Array.from(value).length
 if(length<policy.minimum||length>policy.maximum)return '密码须为8至1024个字符'
 const normalized=value.normalize('NFKC').toLowerCase()
 if(policy.common.includes(normalized.trim())||new Set(normalized).size<3||!value.trim())return '密码过于常见或容易猜测，请使用不常见的密码或密码短语'
 return ''
}
