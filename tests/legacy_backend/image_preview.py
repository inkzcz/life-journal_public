"""Metadata-free, bounded previews. No cache writes on GET; backups remain immutable."""
import io,warnings
from PIL import Image,ImageOps,UnidentifiedImageError
from fastapi import HTTPException

def legacy_preview(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {'JPEG','PNG','WEBP'} or image.width*image.height>50_000_000:raise ValueError()
                oriented=ImageOps.exif_transpose(image);oriented.thumbnail((640,640))
                clean=Image.new('RGB',oriented.size,'white')
                if 'A' in oriented.getbands():clean.paste(oriented.convert('RGB'),mask=oriented.getchannel('A'))
                else:clean.paste(oriented.convert('RGB'))
                result=io.BytesIO();clean.save(result,format='WEBP',quality=80);return result.getvalue()
    except (UnidentifiedImageError,Image.DecompressionBombError,Image.DecompressionBombWarning,OSError,ValueError):
        raise HTTPException(415,'照片无法生成安全预览') from None
