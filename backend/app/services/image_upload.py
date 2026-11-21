"""Shared validated image bytes; original is preserved, derived pixels strip metadata."""
import hashlib,io,re,warnings
from datetime import datetime
from PIL import Image,ImageOps,UnidentifiedImageError
from fastapi import HTTPException


def prepare_image(data,filename):
    if len(data)>10*1024*1024:raise HTTPException(413,'单张图片最多10MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {'JPEG','PNG','WEBP'} or image.width*image.height>20_000_000 or getattr(image,'n_frames',1)!=1:raise ValueError()
                fmt=image.format;width,height=image.size
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                captured_on=None
                try:
                    exif=image.getexif(); original=exif.get_ifd(34665).get(36867) or exif.get(36867)
                    if original:captured_on=datetime.strptime(str(original),'%Y:%m:%d %H:%M:%S').date()
                except (ValueError,TypeError,KeyError,AttributeError):pass
                image.load();oriented=ImageOps.exif_transpose(image);oriented.thumbnail((1600,1600))
                # Fresh pixels only: no EXIF/GPS, XMP, comments, ICC or original metadata.
                clean=Image.new('RGB',oriented.size,'white')
                if 'A' in oriented.getbands():clean.paste(oriented.convert('RGB'),mask=oriented.getchannel('A'))
                else:clean.paste(oriented.convert('RGB'))
                buffer=io.BytesIO();clean.save(buffer,format='WEBP',quality=85);preview=buffer.getvalue()
                preview_width,preview_height=clean.size
                small=clean.copy();small.thumbnail((640,640));buffer=io.BytesIO();small.save(buffer,format='WEBP',quality=80);thumbnail=buffer.getvalue()
    except (UnidentifiedImageError,Image.DecompressionBombError,Image.DecompressionBombWarning,ValueError,OSError,SyntaxError):
        raise HTTPException(415,'仅支持有效的静态JPEG、PNG、WebP（最多2000万像素）') from None
    metadata=dict(captured_on=captured_on,filename=re.sub(r'[\x00-\x1f\x7f]','',(filename or 'image').replace('\\','/').split('/')[-1])[:255] or 'image',
                  mime_type={'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}[fmt],size=len(data),width=width,height=height,
                  preview_width=preview_width,preview_height=preview_height,thumbnail_sha256=hashlib.sha256(thumbnail).hexdigest(),
                  sha256=hashlib.sha256(data).hexdigest(),preview_sha256=hashlib.sha256(preview).hexdigest())
    return {'original':data,'preview.webp':preview,'thumbnail.webp':thumbnail},metadata
