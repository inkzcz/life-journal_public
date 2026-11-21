"""Writing preferences cannot override business schemas, permissions or privacy."""
import hashlib,json
from pydantic import Field,ConfigDict
from ..archive_schemas import StrictModel

class Preferences(StrictModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    require_start:bool=False
    require_end:bool=False
    organize_by_day:bool=True
    day_headings:bool=True
    suggest_tags:bool=True
    itinerary_summary:bool=False
    formal_food_marks:bool=True
    photos_by_date:bool=True
    travel_summary:bool=False
    food_shop:bool=True
    food_date:bool=True
    food_city:bool=True
    food_address:bool=False
    food_review:bool=True
    food_link_travel:bool=False
    photos_by_restaurant:bool=True
    style:str=Field('自然、真实，不编造未提供的事实。',max_length=4000)


def merged(*layers):
    from .syntax import registry
    values=Preferences().model_dump()
    for layer in layers:
        if layer is not None:values.update(Preferences.model_validate(layer).model_dump(exclude_unset=True))
    rules=Preferences.model_validate(values).model_dump()
    canonical=json.dumps({'rule_version':1,'preferences':rules,'syntax':registry()},ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return {'rule_version':1,'digest':hashlib.sha256(canonical.encode()).hexdigest(),'preferences':rules,
            'hard_constraints':['existing-admin-and-csrf','draft-only','current-schema-and-template-version','validated-field-types',
                                'explicit-media-ownership','no-guessed-media-identities','no-silent-overwrite','no-invented-factual-dates']}
