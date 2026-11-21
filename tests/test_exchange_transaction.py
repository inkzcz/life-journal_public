"""Normal API and future imports share one caller-owned transaction."""
import pytest
from sqlalchemy import select
from fastapi import HTTPException
from test_content import client,make_type,record_payload
from test_api import reset_limiter,SessionLocal
from app.models import AdminUser
from app.content_models import ContentRecord,RecordRevision
from app.content_schemas import RecordCreate
from app.services.content import create_record_in_transaction


def test_failed_second_record_rolls_back_first_with_revision_and_places(client):
    t=make_type(client)
    payload=record_payload(t);payload.update(status='draft',body='@l 合成原子事务城市')
    with SessionLocal() as db:
        actor=db.scalar(select(AdminUser.user_id))
        first=create_record_in_transaction(db,RecordCreate.model_validate(payload),actor)
        rid=first.id
        assert db.get(RecordRevision,(rid,1)) is not None
        bad=payload|{'values':{'unknown-field':'not allowed'}}
        with pytest.raises(HTTPException):create_record_in_transaction(db,RecordCreate.model_validate(bad),actor)
        db.rollback()
    with SessionLocal() as db:
        assert db.get(ContentRecord,rid) is None
        assert db.get(RecordRevision,(rid,1)) is None
        from app.archive_models import Place
        assert db.scalar(select(Place.id).where(Place.name=='合成原子事务城市')) is None
