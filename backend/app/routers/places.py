from uuid import UUID
from typing import Literal
from pydantic import Field
from fastapi import APIRouter,Depends
from ..dependencies import db_dep,require_dynamic_blog
from ..archive_schemas import StrictModel
from ..content_schemas import DeleteIn
from ..services import places
from ..services.archive import place,place_data
router=APIRouter(prefix='/api/admin/archive/places',dependencies=[Depends(require_dynamic_blog)])
class Merge(StrictModel):
    target_id:UUID
    expected_revision:int=Field(ge=1)
    target_revision:int=Field(ge=1)
    confirmation:Literal['合并地点']
@router.delete('/{id}')
def remove(id:UUID,data:DeleteIn,db=Depends(db_dep)):return places.delete_place(db,str(id),data.expected_revision)
@router.get('/{id}/duplicates')
def duplicates(id:UUID,db=Depends(db_dep)):return places.duplicates(db,str(id))
@router.get('/{id}/merge-preview')
def preview(id:UUID,target_id:UUID,db=Depends(db_dep)):
    return {'source':place_data(place(db,id)),'target':place_data(place(db,target_id)),'references':places.usages(db,str(id))}
@router.post('/{id}/merge')
def merge(id:UUID,data:Merge,db=Depends(db_dep),actor=Depends(require_dynamic_blog)):
    return places.merge(db,str(id),str(data.target_id),data.expected_revision,data.target_revision,actor.id)
