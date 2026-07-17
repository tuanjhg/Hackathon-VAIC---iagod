from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.repositories.product_repository import ProductRepository
from src.schemas.common import CompareRequest
from src.schemas.product import ComparisonResponse
from src.services.comparison_service import ComparisonService

router = APIRouter(prefix="/compare", tags=["compare"])


@router.post("", response_model=ComparisonResponse)
def compare_products(request: CompareRequest, db: Session = Depends(get_db)) -> ComparisonResponse:
    return ComparisonService(ProductRepository(db)).compare(request.product_ids)

