from decimal import Decimal
from uuid import UUID

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models.product import Product, ProductStatus
from app.models.user import User, UserRole
from app.repositories.product import ProductRepository
from app.schemas.product import ProductCreate, ProductSort, ProductUpdate


class ProductService:
    def __init__(self, products: ProductRepository) -> None:
        self.products = products

    async def get(self, product_id: UUID) -> Product:
        product = await self.products.get(product_id)
        if product is None:
            raise NotFoundError("product_not_found")
        return product

    async def list_(
        self,
        *,
        q: str | None,
        category_id: UUID | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        status: ProductStatus | None,
        sort: ProductSort,
        page: int,
        page_size: int,
    ) -> tuple[list[Product], int]:
        return await self.products.list_(
            q=q,
            category_id=category_id,
            min_price=min_price,
            max_price=max_price,
            status=status,
            sort=sort,
            page=page,
            page_size=page_size,
        )

    async def create(self, payload: ProductCreate, seller: User) -> Product:
        if seller.role not in (UserRole.SELLER, UserRole.ADMIN):
            raise PermissionDeniedError("only_sellers_can_create_products")
        if await self.products.get_by_sku(payload.sku):
            raise ConflictError("sku_taken")
        product = Product(
            sku=payload.sku,
            name=payload.name,
            description=payload.description,
            price=payload.price,
            category_id=payload.category_id,
            seller_id=seller.id,
            stock_quantity=payload.stock_quantity,
            status=(
                ProductStatus.OUT_OF_STOCK if payload.stock_quantity == 0 else ProductStatus.ACTIVE
            ),
        )
        return await self.products.create(product)

    async def update(self, product_id: UUID, payload: ProductUpdate, actor: User) -> Product:
        product = await self.get(product_id)
        self._assert_can_mutate(product, actor)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(product, key, value)
        return product

    async def soft_delete(self, product_id: UUID, actor: User) -> None:
        product = await self.get(product_id)
        self._assert_can_mutate(product, actor)
        await self.products.soft_delete(product)

    @staticmethod
    def _assert_can_mutate(product: Product, actor: User) -> None:
        if actor.role == UserRole.ADMIN:
            return
        if product.seller_id != actor.id:
            raise PermissionDeniedError("not_product_owner")
