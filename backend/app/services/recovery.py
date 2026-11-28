"""Explicit recovery boundaries. Never deletes a shared resource or any media file."""
from datetime import datetime,timedelta,timezone
from copy import deepcopy
import logging
import re
from fastapi import HTTPException
from sqlalchemy import select,delete,or_,and_,func
from sqlalchemy.exc import IntegrityError,OperationalError,DBAPIError
from sqlalchemy.orm.exc import StaleDataError
from ..models import now
from ..content_models import ContentRecord,RecordRevision,RecordBodyMedia,RevisionMediaRef
from ..archive_models import MediaAsset,RecordMedia,RecordLink,RecordPlace,Place,RecordMarkedPlace
from ..life_models import TripPlan,TripActivity,ActivityMedia,PhotoAnnotation
from ..template_models import RecordTemplate,TemplateVersion
from ..blog_models import NavigationItem
from ..archive_schemas import Connections as ConnectionsIn
from ..life_schemas import LifeIn
from .archive import write_lock,replace_connections
from .content import record_data,revision_snapshot,fields_for,record_values,get_type
from .life import save_life


def db_now(db):
    value=db.scalar(select(func.current_timestamp()))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def check_revision(r,expected):
    if r.revision!=expected:raise HTTPException(409,'记录已更新，请重新读取；未保存的修改仍保留')


def warnings(db,r):
    messages=['永久删除文章只解除专属文件夹绑定，保留文件夹及所有媒体，不会清理共享原图。']
    if not get_type(db,r.type_id).active:messages.append('内容类型已停用；恢复后仍保留原类型，不会在前台显示')
    binding=db.get(RecordTemplate,r.id)
    if binding:
        from ..template_models import ContentTemplate
        if not db.get(ContentTemplate,binding.template_id).active:messages.append('原模板已停用；保留不可变模板版本')
    count=db.scalar(select(func.count()).select_from(RecordLink).join(ContentRecord,RecordLink.target_id==ContentRecord.id).where(RecordLink.source_id==r.id,ContentRecord.deleted_at.is_not(None)))
    if count:messages.append(f'{count} 个关联记录仍在回收站，关系保留但前台隐藏')
    if db.scalar(select(func.count()).select_from(NavigationItem).where(NavigationItem.record_id==r.id)):messages.append('站点导航仍引用此记录；须先移除对应导航才能永久删除')
    return messages


def restore_trash(db,r,actor,expected):
    # Restoring again is a safe no-op, including retries of the original request.
    if r.deleted_at is None:return {'id':r.id,'state':'already_active','revision':r.revision,'warnings':warnings(db,r)}
    check_revision(r,expected)
    r.deleted_at=None;r.updated_at=db_now(db);r.revision+=1
    db.flush();revision_snapshot(db,r,actor)
    return {'id':r.id,'state':'restored','revision':r.revision,'warnings':warnings(db,r)}


def _recovery_failure(exc):
    """Public categories only: never stringify DB errors, statements or parameters."""
    if isinstance(exc,HTTPException):
        code='request_conflict' if exc.status_code==409 else 'request_rejected'
        if exc.status_code==409 and isinstance(exc.detail,str):
            if '记录已更新' in exc.detail:code='revision_conflict'
            elif '导航' in exc.detail:code='reference_conflict'
        return {'status':exc.status_code,'code':code,'error':exc.detail}
    if isinstance(exc,IntegrityError):
        return {'status':409,'code':'constraint_conflict','error':'引用约束冲突，此条已回滚；请检查资源引用后重试'}
    if isinstance(exc,StaleDataError):
        return {'status':409,'code':'concurrent_update','error':'记录正被其他操作修改，此条已回滚；请重新读取后重试'}
    if isinstance(exc,OperationalError):
        state=getattr(exc.orig,'sqlstate',None)
        # SQLite error numbers, not driver messages or embedded SQL.
        number=getattr(exc.orig,'sqlite_errorcode',0)
        if (type(state) is str and state in {'40001','40P01','55P03'}) or (type(number) is int and (number & 255) in {5,6}):
            return {'status':409,'code':'concurrent_update','error':'数据库正忙或发生并发修改，此条已回滚；请稍后重试'}
        return {'status':503,'code':'database_unavailable','error':'数据库暂不可用，此条已回滚；请稍后重试'}
    if isinstance(exc,DBAPIError):
        return {'status':500,'code':'database_error','error':'数据库操作失败，此条已回滚；请检查服务状态'}
    return {'status':500,'code':'unexpected_error','error':'操作未完成，此条已回滚；请检查服务状态'}


_recovery_logger=logging.getLogger(__name__)
# These identifiers describe our schema, never driver-provided free text.
_logged_constraints=frozenset({
    'article_options_record_id_fkey','experiences_record_id_fkey',
    'experience_media_record_id_entry_id_fkey','experience_media_media_id_fkey',
    'activity_experiences_record_id_entry_id_fkey','activity_experiences_activity_id_fkey',
    'record_revisions_record_id_fkey','record_templates_record_id_fkey',
    'trip_activities_record_id_fkey','trip_activity_media_activity_id_fkey',
    'food_occurrences_record_id_fkey','navigation_items_record_id_fkey',
})
_logged_states=frozenset({'23503','23505','23514','23502','40001','40P01','55P03','08000','08003','08006','57P01','57014'})
_logged_sqlite_codes=frozenset({5,6,19,261,262,275,517,787,1299,1555,2067})

def recovery_failure(exc):
    failure=_recovery_failure(exc)
    if isinstance(exc,HTTPException):return failure
    # Deliberately omit exc_info: exception reprs contain SQL and parameters.
    kind=('IntegrityError' if isinstance(exc,IntegrityError) else
          'StaleDataError' if isinstance(exc,StaleDataError) else
          'OperationalError' if isinstance(exc,OperationalError) else
          'DBAPIError' if isinstance(exc,DBAPIError) else 'UnexpectedError')
    diagnostic={'category':failure['code'],'exception_type':kind}
    if isinstance(exc,DBAPIError):
        state=getattr(exc.orig,'sqlstate',None)
        if type(state) is str and state in _logged_states:diagnostic['sqlstate']=state
        number=getattr(exc.orig,'sqlite_errorcode',None)
        if type(number) is int and number in _logged_sqlite_codes:diagnostic['sqlite_code']=number
        constraint=getattr(getattr(exc.orig,'diag',None),'constraint_name',None)
        if type(constraint) is str and re.fullmatch(r'[a-z][a-z0-9_]{0,62}',constraint) and constraint in _logged_constraints:
            diagnostic['constraint']=constraint
    _recovery_logger.warning('recovery_operation_failed',extra={'recovery_diagnostic':diagnostic})
    return failure


def purge(db,r,expected):
    if r.deleted_at is None:raise HTTPException(409,'只能永久删除回收站中的记录')
    check_revision(r,expected)
    if db.scalar(select(NavigationItem.id).where(NavigationItem.record_id==r.id).limit(1)):
        raise HTTPException(409,'站点导航仍引用此记录，请先移除对应导航后再清理')
    from ..v5_models import RecordMediaFolder,FoodOccurrence
    db.execute(delete(RecordMediaFolder).where(RecordMediaFolder.record_id==r.id))
    db.execute(delete(FoodOccurrence).where(FoodOccurrence.record_id==r.id))
    activities=select(TripActivity.id).where(TripActivity.record_id==r.id)
    # 0019 source-derived indexes have RESTRICT children. Delete association
    # leaves before either their source experiences or itinerary activities.
    from ..experience_models import ArticleOptions,Experience,ExperienceMedia,ActivityExperience
    db.execute(delete(ActivityExperience).where(or_(ActivityExperience.record_id==r.id,ActivityExperience.activity_id.in_(activities))))
    db.execute(delete(ExperienceMedia).where(ExperienceMedia.record_id==r.id))
    db.execute(delete(Experience).where(Experience.record_id==r.id))
    db.execute(delete(ArticleOptions).where(ArticleOptions.record_id==r.id))
    db.execute(delete(ActivityMedia).where(ActivityMedia.activity_id.in_(activities)))
    from ..tag_models import RecordTag
    from ..archive_models import RevisionPlaceRef
    for model in [RecordMarkedPlace,RevisionPlaceRef,RevisionMediaRef,RecordBodyMedia,RecordTag,TripActivity,TripPlan,PhotoAnnotation,RecordMedia,RecordPlace,RecordTemplate,RecordRevision]:
        db.execute(delete(model).where(model.record_id==r.id))
    # Incoming edges must be removed to satisfy RESTRICT; target resources survive.
    db.execute(delete(RecordLink).where(or_(RecordLink.source_id==r.id,RecordLink.target_id==r.id)))
    db.delete(r);db.flush()


def cleanup_batch(db,days,limit=50,after=None,on_batch=None):
    if days=='never':return {'removed':0,'errors':[],'policy':'never'}
    cutoff=db_now(db)-timedelta(days=days)
    write_lock(db)
    query=select(ContentRecord).where(ContentRecord.deleted_at<cutoff,ContentRecord.deleted_at>=ContentRecord.created_at,ContentRecord.deleted_at<=ContentRecord.updated_at)
    if after:
        timestamp=datetime.fromisoformat(after[0])
        query=query.where(or_(ContentRecord.deleted_at>timestamp,and_(ContentRecord.deleted_at==timestamp,ContentRecord.id>after[1])))
    rows=list(db.scalars(query.order_by(ContentRecord.deleted_at,ContentRecord.id).limit(limit)))
    cursor=[rows[-1].deleted_at.isoformat(),rows[-1].id] if rows else None
    removed=0;errors=[]
    for r in rows:
        id=r.id
        try:
            with db.begin_nested():purge(db,r,r.revision)
            removed+=1
        except Exception as exc:
            failure=recovery_failure(exc)
            errors.append({'id':id,'reason':failure.pop('error'),**failure})
    result={'removed':removed,'errors':errors,'examined':len(rows),'cursor':cursor}
    if on_batch:on_batch(result)  # Audit progress commits atomically with this batch.
    db.commit()
    return result


def revision_data(row):
    s=row.snapshot
    return {'number':row.number,'created_at':row.created_at.isoformat(),'snapshot':s,
            'scope':{'content':True,'template':'template' in s,'connections':'connections' in s,'life':'life' in s},
            'can_restore_full':all(k in s for k in ['template','connections','life'])}


def restore_history(db,r,row,data,actor):
    check_revision(r,data.expected_revision)
    s=deepcopy(row.snapshot)
    if s.get('type_id')!=r.type_id:raise HTTPException(422,'历史类型不匹配，停止恢复')
    if data.scope=='full' and not revision_data(row)['can_restore_full']:
        raise HTTPException(422,'此早期版本未保存全部结构化资源，只能恢复正文和动态字段')
    # Use the immutable original field schema. Never upgrade/reinterpret old values.
    fields=fields_for(db,r.type_id,s['schema_version'])
    values=record_values(fields,s['values'],False,previous=s['values'])
    template=s.get('template') if 'template' in s else None
    current=db.get(RecordTemplate,r.id)
    if 'template' not in s and current:
        version=db.get(TemplateVersion,(current.template_id,current.version))
        if version.schema_version!=s['schema_version']:raise HTTPException(422,'早期快照没有匹配的模板绑定，不能安全恢复')
    if template:
        version=db.get(TemplateVersion,(template['id'],template['version']))
        if not version or (version.type_id,version.schema_version)!=(r.type_id,s['schema_version']):raise HTTPException(422,'历史模板版本不匹配')
        if current:current.template_id=template['id'];current.version=template['version']
        else:db.add(RecordTemplate(record_id=r.id,template_id=template['id'],version=template['version']))
    elif 'template' in s and current:db.delete(current)
    r.body_format=s.get('body_format',1)
    # Snapshot-bound place identity survives renames and merges; no name guessing.
    from .places import canonical
    db.execute(delete(RecordMarkedPlace).where(RecordMarkedPlace.record_id==r.id))
    for binding in s.get('marked_places',[]):
        target=canonical(db,binding['place_id'])
        if target!=binding['place_id'] and not data.resolve_place_aliases:raise HTTPException(409,'标记地点已合并，请确认别名映射')
        if db.get(Place,target) is None:raise HTTPException(409,'标记地点历史身份缺失，拒绝恢复')
        db.add(RecordMarkedPlace(record_id=r.id,source_key=binding['source_key'],place_id=target))
    r.summary=s.get('summary','')
    r.title=s['title'];r.body=s['body'];r.values=values;r.schema_version=s['schema_version']
    from datetime import date
    r.display_date=date.fromisoformat(s['display_date'])
    if 'article' in s:
        from ..content_schemas import ArticleOptionsIn
        from .experiences import save_options
        save_options(db,r,ArticleOptionsIn.model_validate(s['article']))
    r.status='draft';r.revision+=1;r.updated_at=db_now(db)
    db.flush()
    if data.scope=='full':
        from .places import canonical,snapshot_places
        mapped={id:canonical(db,id) for id in snapshot_places(s)}
        changes={id:target for id,target in mapped.items() if id!=target}
        if changes and not data.resolve_place_aliases:raise HTTPException(409,{'message':'历史地点已经合并；请明确确认映射到保留的目标身份','place_aliases':changes})
        con=s['connections']
        for p in con['places']:p['id']=mapped.get(p['id'],p['id'])
        con['places']=list({p['id']:p for p in con['places']}.values())
        for group in ['activities','photos']:
            for item in s['life'].get(group,[]):
                if item.get('place_id'):item['place_id']=mapped.get(item['place_id'],item['place_id'])
        # Historical snapshots include display-only metadata, never accept it as input.
        connections=ConnectionsIn.model_validate({'media':[{k:m[k] for k in ['id','cover','caption']} for m in con['media']],
            'places':[p['id'] for p in con['places']], 'links':[{'id':x['id'],'label':x['label']} for x in con['links']]})
        replace_connections(db,r,connections)
        auto_places={mapped.get(pid,pid) for pid in s.get('markdown_place_ids',[])}
        for ref in db.scalars(select(RecordPlace).where(RecordPlace.record_id==r.id)):ref.markdown_owned=ref.place_id in auto_places
        save_life(db,r,LifeIn.model_validate(s['life']),derive=False)
        owned=set(s.get('markdown_activity_ids',[]))
        for activity in db.scalars(select(TripActivity).where(TripActivity.record_id==r.id,TripActivity.active.is_(True))):activity.markdown_owned=activity.id in owned
    if 'tag_ids' in s:
        from .tags import replace_tags
        replace_tags(db,r,s['tag_ids'],historical=True)
    revision_snapshot(db,r,actor)
    from ..tag_models import Tag
    deleted_tags=[t.name for t in db.scalars(select(Tag).where(Tag.id.in_(s.get('tag_ids',[])),Tag.deleted_at.is_not(None)))]
    notes=warnings(db,r)+(['历史标签已全局删除，未自动复活：'+ '、'.join(deleted_tags)] if deleted_tags else [])
    return {**record_data(db,r),'recovery_warnings':notes}
