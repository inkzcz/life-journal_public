import uuid
from bisect import bisect_left
from datetime import date,timedelta,datetime,timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select,or_,and_,func
from ..blog_models import SiteConfig
from ..content_models import ContentRecord
from ..experience_models import ArticleOptions
from ..life_models import TripPlan,TripActivity
from ..services.blog import readable,summaries
from ..services.archive import write_lock
from .models import Anniversary
from .dates import DateRule,occurrences,years_at
from .schemas import NotifyConfig
KEY='anniversary-notify'

def config(db):
    c=db.scalar(select(SiteConfig).where(SiteConfig.key==KEY))
    return ((c.revision,c.value) if c else (0,{'enabled':False,'url_template':'','timezone':'Asia/Shanghai','time':'09:00'}))

def today(db):return datetime.now(ZoneInfo(config(db)[1]['timezone'])).date()

def list_events(db,start,end,count=None):
    items=[];current=today(db)
    for e in db.scalars(select(Anniversary).where(Anniversary.active.is_(True)).order_by(Anniversary.id)):
        rule=DateRule.model_validate(e.rule)
        for d in occurrences(rule,start,end):
            items.append({'id':e.id,'name':e.name,'kind':e.kind,'date':d.isoformat(),'days_left':(d-current).days,'years':years_at(rule,d),'calendar_type':rule.calendar,'revision':e.revision})
    items.sort(key=lambda x:(x['date'],x['name'],x['id']))
    return items[:count] if count else items

def memories(db,event,page=1):
    rule=DateRule.model_validate(event.rule)
    # Dynamic query: newly backdated articles immediately participate, no copied body.
    ranges=list(db.execute(readable().with_only_columns(ContentRecord.id,ContentRecord.display_date,ArticleOptions.end_date,TripPlan.start_date,TripPlan.end_date).outerjoin(ArticleOptions,ArticleOptions.record_id==ContentRecord.id).outerjoin(TripPlan,TripPlan.record_id==ContentRecord.id)))
    ids=set();dates=[]
    if ranges:
        earliest=min(d for x in ranges for d in (x.display_date,x.start_date) if d is not None)
        first_activity=db.scalar(select(func.min(TripActivity.day)).where(TripActivity.active.is_(True),TripActivity.record_id.in_(readable().with_only_columns(ContentRecord.id))))
        if first_activity:earliest=min(earliest,first_activity)
        last=today(db)
        while earliest<=last:
            end=min(last,earliest+timedelta(days=366*100))
            dates.extend(occurrences(rule,earliest,end));earliest=end+timedelta(days=1)
    dates=sorted(set(dates))
    def covered(start,end):
        if start is None:return False
        i=bisect_left(dates,start)
        return i<len(dates) and dates[i]<=(end or start)
    for rid,start,end,trip_start,trip_end in ranges:
        if covered(start,end) or covered(trip_start,trip_end):ids.add(rid)
    # Explicit day activities also match even in old records without a plan range.
    for i in range(0,len(dates),1000):
        ids.update(db.scalars(select(TripActivity.record_id).where(TripActivity.day.in_(dates[i:i+1000]),TripActivity.active.is_(True),TripActivity.record_id.in_(readable().with_only_columns(ContentRecord.id)))))
    manual=set(event.memories)
    record_dates={r[0]:r[1] for r in ranges}
    ordered=sorted((ids-manual)&set(record_dates),key=lambda rid:(-record_dates[rid].toordinal(),rid))
    selected=ordered[(page-1)*24:page*24]
    return {'memory_page':page,'day_memory_total':len(ordered),'memory_page_size':24,'day_memories':summaries(db,readable().where(ContentRecord.id.in_(selected)).order_by(ContentRecord.display_date.desc(),ContentRecord.id)), 'dedicated_memories':summaries(db,readable().where(ContentRecord.id.in_(manual)).order_by(ContentRecord.display_date.desc(),ContentRecord.id)), 'note':'当天回忆仅表示日期匹配，不表示文章内容必然与纪念日有关。'}
