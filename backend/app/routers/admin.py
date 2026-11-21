from fastapi import APIRouter, Depends
from ..dependencies import require_admin, get_settings
from ..models import User

router = APIRouter(prefix='/api/admin', dependencies=[Depends(require_admin)])


@router.get('/status')
def status(user: User = Depends(require_admin), settings=Depends(get_settings)):
    return {'username': user.username, 'is_admin': True,
            'features': {'dynamic_blog': True}}
