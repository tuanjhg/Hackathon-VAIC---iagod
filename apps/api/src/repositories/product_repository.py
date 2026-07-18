from decimal import Decimal

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, aliased, joinedload

from src.models import (
    AttributeDefinition,
    Category,
    Inventory,
    Price,
    Product,
    ProductAttributeValue,
    ProductOffer,
    ProductSpec,
)
from src.schemas.product import ProductSearchRequest


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
            joinedload(Product.offers),
        )

    def list_categories(self) -> list[Category]:
        return list(self.db.scalars(select(Category).order_by(Category.name)).all())

    def list_products(
        self,
        *,
        search: str | None = None,
        category: str | None = None,
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
        if category:
            query = query.join(Product.category).where(Category.slug == category)
        if search:
            term = f"%{search.lower()}%"
            query = query.where(
                or_(func.lower(Product.name).like(term), func.lower(Product.brand).like(term))
            )
        if brand:
            query = query.where(func.lower(Product.brand) == brand.lower())
        if min_price is not None:
            query = query.where(Price.sale_price > 0, Price.sale_price >= min_price)
        if max_price is not None:
            query = query.where(Price.sale_price > 0, Price.sale_price <= max_price)
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
            query = query.order_by((Price.sale_price <= 0).asc(), Price.sale_price.asc())
        elif sort == "price_desc":
            query = query.order_by((Price.sale_price <= 0).asc(), Price.sale_price.desc())
        else:
            query = query.order_by(
                Product.featured.desc(), (Price.sale_price > 0).desc(), Product.id.asc()
            )
        products = list(
            self.db.scalars(query.offset((page - 1) * page_size).limit(page_size)).unique().all()
        )
        return products, total

    def get_by_slug(self, slug: str) -> Product | None:
        return self.db.scalar(self._base_query().where(Product.slug == slug))

    def get_by_identifier(self, identifier: str) -> Product | None:
        if identifier.isdigit():
            product = self.db.scalar(self._base_query().where(Product.id == int(identifier)))
            if product is not None:
                return product
        return self.get_by_slug(identifier)

    def get_by_ids(self, product_ids: list[int]) -> list[Product]:
        products = list(self.db.scalars(self._base_query().where(Product.id.in_(product_ids))).unique())
        order = {product_id: index for index, product_id in enumerate(product_ids)}
        return sorted(products, key=lambda product: order[product.id])

    def search_facets(self, request: ProductSearchRequest) -> tuple[list[Product], int]:
        category = self.db.scalar(select(Category).where(Category.code == request.category_code))
        if category is None or not category.is_active:
            raise ValueError(f"Unknown category_code: {request.category_code}")
        definitions = {
            item.attribute_key: item
            for item in self.db.scalars(
                select(AttributeDefinition).where(
                    AttributeDefinition.category_id == category.id,
                    AttributeDefinition.attribute_key.in_(request.filters),
                    AttributeDefinition.filterable.is_(True),
                )
            )
        }
        unknown = set(request.filters) - set(definitions)
        if unknown:
            raise ValueError("Unknown or non-filterable attributes: " + ", ".join(sorted(unknown)))

        query = (
            self._base_query()
            .where(Product.category_id == category.id, Product.status == "active")
            .outerjoin(
                ProductOffer,
                and_(ProductOffer.product_id == Product.id, ProductOffer.is_current.is_(True)),
            )
        )
        if request.price_min is not None:
            query = query.where(ProductOffer.sale_price >= request.price_min)
        if request.price_max is not None:
            query = query.where(ProductOffer.sale_price <= request.price_max)

        for key, condition in request.filters.items():
            definition = definitions[key]
            facet = aliased(ProductAttributeValue)
            query = query.join(
                facet,
                and_(facet.product_id == Product.id, facet.attribute_id == definition.id),
            )
            if definition.data_type == "number":
                if condition.eq is not None:
                    query = query.where(facet.value_number == condition.eq)
                if condition.gte is not None:
                    query = query.where(facet.value_number >= condition.gte)
                if condition.lte is not None:
                    query = query.where(facet.value_number <= condition.lte)
                if condition.in_values:
                    query = query.where(facet.value_number.in_(condition.in_values))
            elif definition.data_type == "boolean":
                if condition.eq is not None:
                    if not isinstance(condition.eq, bool):
                        raise ValueError(f"{key}.eq must be boolean")
                    query = query.where(facet.value_boolean == condition.eq)
            elif definition.data_type == "text":
                if condition.eq is not None:
                    query = query.where(func.lower(facet.value_text) == str(condition.eq).lower())
                if condition.in_values:
                    query = query.where(
                        func.lower(facet.value_text).in_([str(v).lower() for v in condition.in_values])
                    )
            elif condition.eq is not None:
                query = query.where(facet.value_json == condition.eq)

        count_query = select(func.count()).select_from(query.order_by(None).subquery())
        total = self.db.scalar(count_query) or 0
        sort_fields = {
            "sale_price": ProductOffer.sale_price,
            "display_name": Product.display_name,
            "model_code": Product.model_code,
            "created_at": Product.created_at,
        }
        for sort_item in request.sort:
            column = sort_fields.get(sort_item.field)
            if column is None:
                raise ValueError(f"Unsupported sort field: {sort_item.field}")
            query = query.order_by(column.desc() if sort_item.direction == "desc" else column.asc())
        if not request.sort:
            query = query.order_by(Product.featured.desc(), Product.id)
        products = list(
            self.db.scalars(query.offset(request.offset).limit(request.limit)).unique().all()
        )
        return products, total
