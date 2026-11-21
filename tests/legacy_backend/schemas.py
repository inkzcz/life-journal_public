from datetime import date
from pydantic import BaseModel, Field, field_validator


class JournalIn(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    content:str=Field(default='',max_length=300000)
    entry_date:date | None=None
    category:str=Field(default='',max_length=80)
    tags:list[str]=Field(default_factory=list,max_length=10)

    @field_validator('category')
    @classmethod
    def clean_category(cls, value):
        return value.strip()

    @field_validator('tags')
    @classmethod
    def clean_tags(cls, values):
        result = []
        for value in values:
            value = value.strip()
            if not 1 <= len(value) <= 40:
                raise ValueError('标签须为1至40字符')
            if value not in result:
                result.append(value)
        return result
