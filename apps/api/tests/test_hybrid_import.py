from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.core.database import Base
from src.importers import csv_importer
from src.importers.category_registry import CATEGORY_REGISTRY
from src.importers.csv_importer import ImportOptions
from src.models import (
    ImportBatch,
    Product,
    ProductAttributeValue,
    ProductOffer,
    ProductSpec,
    RawProductRow,
)


def test_import_csv_is_resilient_and_idempotent(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(csv_importer, "SessionLocal", testing_session)
    csv_path = tmp_path / "tu_lanh.csv"
    csv_path.write_text(
        "sku,productidweb,model_code,brand,gia_goc,gia_khuyen_mai,khuyen_mai_qua,"
        "dung_tich_tong,cao,cong_nghe_tiet_kiem_dien\n"
        'RF-1,WEB-1,R100,Samsung Việt Nam,"15.000.000","13.500.000",'
        '"Phiếu mua hàng 500.000 đồng; Trả góp 0%","406 lít","171,5 cm",Có\n'
        ",,,,,,,,,-\n",
        encoding="utf-8",
    )
    config = CATEGORY_REGISTRY["refrigerators"]
    first = csv_importer.import_file(csv_path, config, ImportOptions(batch_size=1))
    second = csv_importer.import_file(
        csv_path, config, ImportOptions(batch_size=2, skip_existing=True)
    )

    assert (first.total_rows, first.success_rows, first.failed_rows) == (2, 1, 1)
    assert first.success_rows + first.failed_rows == first.total_rows
    assert second.skipped_rows == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Product)) == 1
        assert db.scalar(select(func.count()).select_from(ImportBatch)) == 2
        assert db.scalar(select(func.count()).select_from(RawProductRow)) == 4
        product = db.scalar(select(Product).where(Product.sku == "RF-1"))
        assert product is not None
        specs = db.get(ProductSpec, product.id)
        assert specs is not None
        assert specs.raw_specs["dung_tich_tong"] == "406 lít"
        assert specs.normalized_specs["capacity"]["total_liter"] == 406
        assert specs.normalized_specs["dimensions_mm"]["height"] == 1715
        offer = db.scalar(
            select(ProductOffer).where(
                ProductOffer.product_id == product.id, ProductOffer.is_current.is_(True)
            )
        )
        assert offer is not None
        assert offer.sale_price == 13_500_000
        assert offer.gifts[1]["type"] == "installment"
        facets = list(
            db.scalars(
                select(ProductAttributeValue).where(
                    ProductAttributeValue.product_id == product.id
                )
            )
        )
        assert facets


def test_dry_run_does_not_write_database(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(csv_importer, "SessionLocal", sessionmaker(bind=engine))
    csv_path = tmp_path / "may_tinh_bang.csv"
    csv_path.write_text("sku,brand,ram\nTAB-1,Samsung,8 GB\n", encoding="utf-8")
    report = csv_importer.import_file(
        csv_path, CATEGORY_REGISTRY["tablets"], ImportOptions(dry_run=True)
    )
    assert report.success_rows == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Product)) == 0
