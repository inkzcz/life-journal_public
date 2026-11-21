"""Private topic views of the existing published article graph."""
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, cast, String
from sqlalchemy.orm import defer
from ..dependencies import db_dep, current_user
from ..experience_models import Experience
from ..content_models import ContentRecord
from ..services.blog import readable
router = APIRouter(prefix='/api/experiences', dependencies=[Depends(current_user)])

@router.get('')
def listing(kind:Literal['l','f','m','s','g','t'], page:int=Query(1,ge=1,le=100000), transport_type:str=Query('',max_length=100), db=Depends(db_dep)):
    q=select(Experience,ContentRecord).options(defer(ContentRecord.body),defer(ContentRecord.values)).join(ContentRecord,ContentRecord.id==Experience.record_id).where(Experience.active.is_(True),Experience.kind==kind,ContentRecord.id.in_(readable().with_only_columns(ContentRecord.id)))
    if transport_type:q=q.where(Experience.fields['transport_type'].as_string()==transport_type)
    total=db.scalar(select(func.count()).select_from(q.subquery()))
    # ISO calendar date projection is portable between PostgreSQL and SQLite.
    day=func.coalesce(func.nullif(Experience.fields['date'].as_string(),''),func.nullif(func.substr(Experience.fields['departure_at'].as_string(),1,10),''),cast(ContentRecord.display_date,String))
    rows=db.execute(q.order_by(day.desc(),Experience.record_id,Experience.position).offset((page-1)*24).limit(24))
    return {'items':[{'id':e.id,'kind':e.kind,'name':e.name,'fields':{k:v for k,v in e.fields.items() if k!='media_ids'},'media_ids':e.fields.get('media_ids',[]),'record_id':r.id,'record_title':r.title,'display_date':r.display_date.isoformat(),'anchor':'entry-'+e.id} for e,r in rows], 'total':total,'page':page,'page_size':24}

@router.get('/trips')
def trips(page:int=Query(1,ge=1,le=100000),db=Depends(db_dep)):
    from ..experience_models import ArticleOptions
    from ..life_models import TripPlan
    from ..services.blog import page_records
    from sqlalchemy import or_,and_
    q=readable().outerjoin(ArticleOptions,ArticleOptions.record_id==ContentRecord.id).outerjoin(TripPlan,TripPlan.record_id==ContentRecord.id).where(or_(ArticleOptions.travel_enabled.is_(True),and_(ArticleOptions.record_id.is_(None),TripPlan.start_date.is_not(None))))
    return page_records(db,q,page,24)

@router.get('/places')
def places(page:int=Query(1,ge=1,le=100000),db=Depends(db_dep)):
    from ..archive_models import Place,RecordPlace
    q=select(Place).where(Place.id.in_(select(RecordPlace.place_id).where(RecordPlace.record_id.in_(readable().with_only_columns(ContentRecord.id)))))
    total=db.scalar(select(func.count()).select_from(q.subquery()))
    return {'items':[{'id':p.id,'name':p.name,'city':p.city,'region':p.region,'records':[{'id':rid,'title':title} for rid,title in db.execute(readable().with_only_columns(ContentRecord.id,ContentRecord.title).join(RecordPlace,RecordPlace.record_id==ContentRecord.id).where(RecordPlace.place_id==p.id).limit(50))]} for p in db.scalars(q.order_by(Place.name,Place.id).offset((page-1)*24).limit(24))],'total':total,'page':page,'page_size':24}
