from contextlib import asynccontextmanager
import logging
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sigillum.config import get_settings
from sigillum.infrastructure.database.session import Base, engine, SessionLocal
from sigillum.infrastructure.database import models
from sigillum.infrastructure.security import hash_password
from sigillum.api.routes import router

settings=get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env.lower() != "production":
        # Convenience for local/demo runs. Production schema is migration-managed.
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            demo_users = [
                ("creator@orbita.demo", "ORBITA Creator", "creator"),
                ("reviewer@orbita.demo", "ORBITA Reviewer", "reviewer"),
                ("owner@orbita.demo", "ORBITA Brand Owner", "brand_owner"),
                ("admin@orbita.demo", "ORBITA Administrator", "administrator"),
            ]
            for email, name, role in demo_users:
                user = db.query(models.User).filter(models.User.email == email).first()
                if not user:
                    db.add(
                        models.User(
                            email=email,
                            display_name=name,
                            role=role,
                            password_hash=hash_password(settings.sigillum_demo_password),
                        )
                    )
                else:
                    user.password_hash = hash_password(settings.sigillum_demo_password)
            db.commit()
    yield

app=FastAPI(title=settings.app_name,version="0.1.0",description="Evidence-first brand assurance with deterministic adjudication and human approval.",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origin_list,allow_credentials=True,allow_methods=["GET","POST","OPTIONS"],allow_headers=["Authorization","Content-Type","X-Request-ID"])

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

@app.exception_handler(HTTPException)
async def structured_http_error(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code":"HTTP_ERROR", "message":str(exc.detail)}
    detail = {**detail, "request_id":getattr(request.state, "request_id", None)}
    return JSONResponse(status_code=exc.status_code, content={"detail":detail}, headers=exc.headers)

@app.exception_handler(RequestValidationError)
async def structured_validation_error(request: Request, exc: RequestValidationError):
    issues = [{"location":[str(part) for part in item.get("loc",[])],"message":item.get("msg","Invalid value"),"type":item.get("type","validation_error")} for item in exc.errors()]
    return JSONResponse(status_code=422, content={"detail":{"code":"VALIDATION_ERROR","message":"Request validation failed.","issues":issues,"request_id":getattr(request.state,"request_id",None)}})

@app.exception_handler(Exception)
async def structured_unhandled_error(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logging.getLogger("sigillum.api").exception("Unhandled API error", extra={"request_id":request_id,"error_type":type(exc).__name__})
    return JSONResponse(status_code=500, content={"detail":{"code":"INTERNAL_ERROR","message":"An internal error occurred. The request ID can be used for investigation.","request_id":request_id}})
app.include_router(router,prefix=settings.api_v1_prefix)

@app.get("/health/live",tags=["health"])
def live(): return {"status":"ok"}

@app.get("/health/ready",tags=["health"])
def ready(response: Response):
    try:
        with engine.connect() as connection: connection.execute(text("SELECT 1"))
        from sigillum.modules.knowledge.brand_pack import BrandPack

        active_pack = BrandPack()
        pack_version = active_pack.version()
        pack_hash = active_pack.fingerprint()
        settings.storage_root.mkdir(parents=True, exist_ok=True)
        return {
            "status": "ready",
            "database": "connected",
            "storage": "available",
            "brand_pack": "loaded",
            "brand_pack_version": pack_version,
            "brand_pack_hash": pack_hash,
            "review_execution": "synchronous_api",
        }
    except Exception as exc:
        response.status_code = 503
        return {"status":"not_ready","database":"unavailable","error":type(exc).__name__}
