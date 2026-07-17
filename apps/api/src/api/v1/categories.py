from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.repositories.product_repository import ProductRepository
from src.schemas.product import CategoryRead

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryRead]:
    return [CategoryRead.model_validate(item) for item in ProductRepository(db).list_categories()]

