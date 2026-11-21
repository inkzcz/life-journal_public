import secrets
from fastapi import Request, Response


async def csrf_guard(request:Request,call_next):
    if request.method in ('POST','PUT','PATCH','DELETE'):
        token=request.cookies.get('life_csrf')
        header=request.headers.get('x-csrf-token')
        if not token or not header or not secrets.compare_digest(token,header):
            return Response('CSRF validation failed',status_code=403)
        # Require browser fetch requests to come from the same site (Fetch Metadata).
        if request.headers.get('sec-fetch-site','same-origin') not in ('same-origin','none'):
            return Response('Cross-site request denied',status_code=403)
    if request.method in ('POST','PUT','PATCH','DELETE'):
        from starlette.concurrency import run_in_threadpool
        from fastapi import HTTPException
        from .db import engine
        from .services.write_barrier import writer
        barrier=writer(engine)
        try:
            await run_in_threadpool(barrier.__enter__)
        except HTTPException as e:
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail':e.detail},status_code=e.status_code,headers=e.headers)
        try:response=await call_next(request)
        finally:await run_in_threadpool(barrier.__exit__,None,None,None)
    else:response=await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
