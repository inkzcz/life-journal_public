"""One SQL authority for editor, reader, filtering and counts; no data writes."""
from sqlalchemy import select,func,or_,and_,cast,literal
from ..content_models import ContentRecord,VersionField,FieldDefinition
from ..experience_models import ArticleOptions
from ..life_models import TripPlan,TripActivity
from ..template_models import RecordTemplate,TemplateVersion


def travel_expression(db):
    explicit=select(ArticleOptions.travel_enabled).where(ArticleOptions.record_id==ContentRecord.id).correlate(ContentRecord).scalar_subquery()
    plan=select(TripPlan.record_id).where(TripPlan.record_id==ContentRecord.id,or_(TripPlan.start_date.is_not(None),TripPlan.end_date.is_not(None))).correlate(ContentRecord).exists()
    activity=select(TripActivity.id).where(TripActivity.record_id==ContentRecord.id).correlate(ContentRecord).exists()
    if db.bind.dialect.name=='postgresql':
        from sqlalchemy.dialects.postgresql import JSONPATH
        itinerary=func.jsonb_path_exists(TemplateVersion.config,cast(literal('$.modules[*] ? (@.kind == "itinerary")'),JSONPATH))
    else:
        modules=func.json_each(TemplateVersion.config,'$.modules').table_valued('key','value')
        itinerary=select(literal(1)).select_from(modules).where(func.json_extract(modules.c.value,'$.kind')=='itinerary').correlate(TemplateVersion).exists()
    template=select(RecordTemplate.record_id).join(TemplateVersion,and_(TemplateVersion.template_id==RecordTemplate.template_id,TemplateVersion.number==RecordTemplate.version)).where(RecordTemplate.record_id==ContentRecord.id,itinerary).correlate(ContentRecord).exists()
    field=select(VersionField.field_id).join(FieldDefinition,FieldDefinition.id==VersionField.field_id).where(VersionField.type_id==ContentRecord.type_id,VersionField.version==ContentRecord.schema_version,VersionField.active.is_(True),FieldDefinition.kind=='date',VersionField.name.in_(['出发日期','旅行开始日期']),func.coalesce(VersionField.rules['purpose'].as_string(),'')=='').correlate(ContentRecord).exists()
    return func.coalesce(explicit,or_(plan,activity,template,field))


def record_modes(db,records):
    ids=[r.id for r in records]
    return dict(db.execute(select(ContentRecord.id,travel_expression(db)).where(ContentRecord.id.in_(ids))).all()) if ids else {}
