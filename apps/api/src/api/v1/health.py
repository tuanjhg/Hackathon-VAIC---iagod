from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "needwise-api"}


@router.get("/health/db")
def database_health(db: Session = Depends(get_db)) -> dict[str, object]:
    db.execute(text("SELECT 1"))
    extensions = {
        row.name: row.version
        for row in db.execute(
            text(
                "SELECT extname AS name, extversion AS version FROM pg_extension "
                "WHERE extname IN ('vector', 'pgcrypto')"
            )
        )
    } if db.bind is not None and db.bind.dialect.name == "postgresql" else {}
    return {"status": "ok", "database": "connected", "extensions": extensions}
