from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from src.models import (
    AttributeDefinition,
    ImportBatch,
    ProductAttributeValue,
    ProductOffer,
    ProductSpec,
    RawProductRow,
)


def test_hybrid_tables_and_constraints_are_declared() -> None:
    assert ProductSpec.__table__.primary_key.columns.keys() == ["product_id"]
    assert any(
        isinstance(item, UniqueConstraint)
        and set(item.columns.keys()) == {"batch_id", "row_number"}
        for item in RawProductRow.__table__.constraints
    )
    assert any(isinstance(item, CheckConstraint) for item in ImportBatch.__table__.constraints)
    assert any(isinstance(item, CheckConstraint) for item in AttributeDefinition.__table__.constraints)
    assert any(isinstance(item, CheckConstraint) for item in ProductAttributeValue.__table__.constraints)
    assert any(
        isinstance(item, Index) and item.name == "idx_one_current_offer_per_product"
        for item in ProductOffer.__table__.indexes
    )
