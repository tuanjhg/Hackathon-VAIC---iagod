from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from src.models import Category, Inventory, Price, Product, ProductSpec


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _base_query() -> Select[tuple[Product]]:
        return select(Product).options(
            joinedload(Product.category),
            joinedload(Product.specs),
            joinedload(Product.price),
            joinedload(Product.inventory),
            joinedload(Product.promotion),
        )

    def list_categories(self) -> list[Category]:
        return list(self.db.scalars(select(Category).order_by(Category.name)).all())

    def list_products(
        self,
        *,
        search: str | None = None,
        brand: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        room_area: float | None = None,
        inverter: bool | None = None,
        in_stock: bool | None = None,
        sort: str = "featured",
        page: int = 1,
        page_size: int = 12,
    ) -> tuple[list[Product], int]:
        query = self._base_query().join(Product.price).join(Product.specs).join(Product.inventory)
        if search:
            term = f"%{search.lower()}%"
            query = query.where(
                or_(func.lower(Product.name).like(term), func.lower(Product.brand).like(term))
            )
        if brand:
            query = query.where(func.lower(Product.brand) == brand.lower())
        if min_price is not None:
            query = query.where(Price.sale_price >= min_price)
        if max_price is not None:
            query = query.where(Price.sale_price <= max_price)
        if room_area is not None:
            query = query.where(
                ProductSpec.recommended_area_min <= room_area,
                ProductSpec.recommended_area_max >= room_area,
            )
        if inverter is not None:
            query = query.where(ProductSpec.inverter == inverter)
        if in_stock is not None:
            query = query.where(Inventory.stock_quantity > 0 if in_stock else Inventory.stock_quantity == 0)

        count_query = select(func.count()).select_from(query.order_by(None).subquery())
        total = self.db.scalar(count_query) or 0
        if sort == "price_asc":
            query = query.order_by(Price.sale_price.asc())
        elif sort == "price_desc":
            query = query.order_by(Price.sale_price.desc())
        else:
            query = query.order_by(Product.featured.desc(), Product.rating.desc())
        products = list(
            self.db.scalars(query.offset((page - 1) * page_size).limit(page_size)).unique().all()
        )
        return products, total

    def get_by_slug(self, slug: str) -> Product | None:
        return self.db.scalar(self._base_query().where(Product.slug == slug))

    def get_by_ids(self, product_ids: list[int]) -> list[Product]:
        products = list(self.db.scalars(self._base_query().where(Product.id.in_(product_ids))).unique())
        order = {product_id: index for index, product_id in enumerate(product_ids)}
        return sorted(products, key=lambda product: order[product.id])
