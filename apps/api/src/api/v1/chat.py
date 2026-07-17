from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.repositories.product_repository import ProductRepository
from src.schemas.chat import ChatMessageRequest, ChatResponse, DemoScenario
from src.services.mock_chat_service import MockChatService
from src.services.product_service import ProductService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/messages", response_model=ChatResponse)
def send_message(request: ChatMessageRequest, db: Session = Depends(get_db)) -> ChatResponse:
    service = MockChatService(ProductService(ProductRepository(db)))
    return service.reply(request)


@router.get("/demo-scenarios", response_model=list[DemoScenario])
def demo_scenarios() -> list[DemoScenario]:
    return [
        DemoScenario(title="Phòng ngủ 18m²", message="Tư vấn máy lạnh cho phòng 18m2"),
        DemoScenario(title="Phòng khách 30m²", message="Tư vấn máy lạnh cho phòng 30m2"),
    ]

