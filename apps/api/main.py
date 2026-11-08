from contextlib import asynccontextmanager
import logging
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sigillum.config import get_settings
from sigillum.infrastructure.database.session import engine, SessionLocal, set_database_scope
from sigillum.infrastructure.database.migrations import get_migration_status, upgrade_database
from sigillum.infrastructure.database import models
from sigillum.infrastructure.security import hash_password
from sigillum.infrastructure.storage import S3CompatibleStorage, get_storage, StorageUnavailable
from sigillum.api.routes import router

settings=get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = get_storage(settings)
    if settings.storage_backend == "s3" and settings.app_env.lower() != "production":
        # Local MinIO convenience only. A provider outage must not make the API crash-loop;
        # readiness will report the outage and write requests will fail closed.
        if isinstance(storage, S3CompatibleStorage):
            try:
                storage.ensure_bucket()
            except StorageUnavailable as exc:
                logging.getLogger("sigillum.storage").warning(
                    "Development bucket bootstrap failed",
                    extra={"error_type": type(exc).__name__},
                )
    if settings.app_env.lower() != "production":
        # Local/demo startup applies the same checked-in migrations used by deployments.
        upgrade_database(settings)
        with SessionLocal() as db:
            demo_users = [
                ("creator@orbita.demo", "ORBITA Creator", "creator"),
                ("reviewer@orbita.demo", "ORBITA Reviewer", "reviewer"),
                ("owner@orbita.demo", "ORBITA Brand Owner", "brand_owner"),
                ("admin@orbita.demo", "ORBITA Administrator", "administrator"),
            ]
            tenant_id = "tenant_demo"
            brand_external_id = "brand_orbita_demo"
            for email, name, role in demo_users:
                user = db.scalar(select(models.User).where(models.User.email == email))
                if not user:
                    user = models.User(
                        email=email,
                        display_name=name,
                        role=role,
                        tenant_id=tenant_id,
                        password_hash=hash_password(settings.sigillum_demo_password),
                    )
                    db.add(user)
                    db.flush()
                else:
                    user.password_hash = hash_password(settings.sigillum_demo_password)
                    user.tenant_id = tenant_id
                    user.is_active = True

                # RLS is active on PostgreSQL. Bootstrap is scoped to this known
                # demo user and the exact synthetic tenant/brand being provisioned.
                set_database_scope(
                    db,
                    user_id=user.id,
                    tenant_id=tenant_id,
                    brand_id=brand_external_id,
                    membership_role="administrator",
                )
                tenant = db.get(models.Tenant, tenant_id)
                if not tenant:
                    tenant = models.Tenant(id=tenant_id, name="ORBITA Demo Workspace", is_active=True)
                    db.add(tenant)
                    db.flush()

                brand = db.scalar(
                    select(models.Brand).where(
                        models.Brand.tenant_id == tenant_id,
                        models.Brand.external_id == brand_external_id,
                    )
                )
                if not brand:
                    brand = models.Brand(
                        tenant_id=tenant_id,
                        external_id=brand_external_id,
                        name="ORBITA",
                        is_active=True,
                    )
                    db.add(brand)
                    db.flush()

                # Membership RLS checks the internal Brand primary key, not only
                # the public brand identifier. Refresh the trusted bootstrap scope
                # after the Brand row has been located or created.
                set_database_scope(
                    db,
                    user_id=user.id,
                    tenant_id=tenant_id,
                    brand_id=brand_external_id,
                    brand_record_id=brand.id,
                    membership_role="administrator",
                )

                membership = db.scalar(
                    select(models.Membership).where(
                        models.Membership.user_id == user.id,
                        models.Membership.brand_id == brand.id,
                    )
                )
                if not membership:
                    db.add(
                        models.Membership(
                            user_id=user.id,
                            tenant_id=tenant_id,
                            brand_id=brand.id,
                            role=role,
                            is_active=True,
                        )
                    )
                else:
                    membership.role = role
                    membership.is_active = True
            db.commit()
    yield

app=FastAPI(title=settings.app_name,version="0.1.0",description="Evidence-first brand assurance with deterministic adjudication and human approval.",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origin_list,allow_credentials=True,allow_methods=["GET","POST","PATCH","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type","X-Request-ID"])

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

@app.get("/health/ready", tags=["health"])
def ready(response: Response):
    database_status = "connected"
    database_schema_status = "pending"
    migration_revision = None
    expected_migration_revision = None
    storage_status = "available"
    pack_status = "loaded"
    error_types: list[str] = []

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            migration = get_migration_status(connection, settings)
            database_schema_status = migration["status"]
            migration_revision = migration["current_revision"]
            expected_migration_revision = migration["expected_revision"]
            if database_schema_status != "current":
                error_types.append("DatabaseSchemaNotAtHead")
    except Exception as exc:
        database_status = "unavailable"
        database_schema_status = "unknown"
        error_types.append(type(exc).__name__)

    storage = get_storage(settings)
    try:
        storage.health_check()
    except StorageUnavailable as exc:
        storage_status = "unavailable"
        error_types.append(type(exc).__name__)

    try:
        from sigillum.modules.knowledge.brand_pack import BrandPack

        active_pack = BrandPack()
        pack_version = active_pack.version()
        pack_hash = active_pack.fingerprint()
    except Exception as exc:
        pack_status = "unavailable"
        pack_version = None
        pack_hash = None
        error_types.append(type(exc).__name__)

    ready_state = (
        database_status == "connected"
        and database_schema_status == "current"
        and storage_status == "available"
        and pack_status == "loaded"
    )
    if not ready_state:
        response.status_code = 503

    return {
        "status": "ready" if ready_state else "not_ready",
        "database": database_status,
        "database_schema": database_schema_status,
        "migration_revision": migration_revision,
        "expected_migration_revision": expected_migration_revision,
        "database_dialect": engine.dialect.name,
        "storage": storage_status,
        "storage_driver": storage.driver_name,
        "brand_pack": pack_status,
        "brand_pack_version": pack_version,
        "brand_pack_hash": pack_hash,
        "review_execution": "synchronous_api",
        "errors": error_types,
    }
