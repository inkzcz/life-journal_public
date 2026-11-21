import {VERSION} from './version'
export type BuildInfo={version:string;short_revision:string|null;built_at:string|null;revision_verified:boolean;source_kind:string;fingerprint:string|null}
declare const __BUILD_INFO__:BuildInfo
export const WEB_BUILD:BuildInfo=typeof __BUILD_INFO__==='undefined'?{version:VERSION,short_revision:null,built_at:null,revision_verified:false,source_kind:'unversioned',fingerprint:null}:__BUILD_INFO__
export function consistency(api:BuildInfo){return api.version!==WEB_BUILD.version?'前后端版本不一致':!api.fingerprint||!WEB_BUILD.fingerprint?'构建身份尚未验证':api.fingerprint===WEB_BUILD.fingerprint?'前后端构建标识一致（非镜像完整性校验）':'前后端构建不一致'}
