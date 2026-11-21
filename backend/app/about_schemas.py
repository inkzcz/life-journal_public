from pydantic import Field
from .archive_schemas import StrictModel
class About(StrictModel):
    name:str=Field(default='Life Journal',max_length=100)
    intro:str=Field(default='私人的生活档案馆',max_length=1000)
    body:str=Field(default='',max_length=20000)
    motivation:str=Field(default='',max_length=2000)
    notes:str=Field(default='',max_length=2000)
class AboutEdit(About):
    expected_revision:int=Field(ge=0)
