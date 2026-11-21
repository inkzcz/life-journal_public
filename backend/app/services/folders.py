"""Logical folders never move bytes. All mutations share the archive transaction lock."""
import unicodedata
from fastapi import HTTPException
from sqlalchemy import select,func
from ..archive_models import MediaFolder,MediaAsset

def require_folder(db,id):
    if id is None:return None
    row=db.get(MediaFolder,str(id))
    if not row:raise HTTPException(422,'目标文件夹不存在')
    return row

def folder_data(row):
    return {k:getattr(row,k) for k in ['id','name','parent_id','revision']}

def validate_tree(db,id,parent_id,name):
    rows=list(db.scalars(select(MediaFolder)))
    parents={r.id:r.parent_id for r in rows};parents[id]=str(parent_id) if parent_id else None
    normalized=unicodedata.normalize('NFKC',name).casefold().strip()
    if len(normalized)>100:raise HTTPException(422,'规范化后的文件夹名称过长')
    if any(r.id!=id and r.parent_id==parents[id] and r.normalized_name==normalized for r in rows):raise HTTPException(409,'同一层级已有同名文件夹')
    require_folder(db,parent_id)
    for start in parents:
        seen=set();current=start
        while current is not None:
            if current in seen:raise HTTPException(422,'不能把文件夹移动到自身或其子文件夹中')
            seen.add(current)
            if len(seen)>8:raise HTTPException(422,'文件夹最多8层，移动后的子目录也不能超限')
            current=parents.get(current)
    return normalized
