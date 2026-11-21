"""Curated views of existing media, independent of content types or copies."""
from sqlalchemy import Uuid, ForeignKey, String, Integer
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
class Album(Base):
    __tablename__='photo_albums'
    id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True)
    name:Mapped[str]=mapped_column(String(200))
    cover_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False),ForeignKey('media_assets.id',ondelete='RESTRICT'),nullable=True)
    revision:Mapped[int]=mapped_column(Integer)
class AlbumPhoto(Base):
    __tablename__='photo_album_photos'
    album_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('photo_albums.id',ondelete='RESTRICT'),primary_key=True)
    media_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),ForeignKey('media_assets.id',ondelete='RESTRICT'),primary_key=True,index=True)
    position:Mapped[int]=mapped_column(Integer)
