from app.core.exceptions import InvariantViolationError
from app.models.order import OrderStatus

ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.PAYMENT_PROCESSING, OrderStatus.CANCELLED},
    OrderStatus.PAYMENT_PROCESSING: {
        OrderStatus.CONFIRMED,
        OrderStatus.PENDING,
        OrderStatus.CANCELLED,
    },
    OrderStatus.CONFIRMED: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}

CANCELLABLE: set[OrderStatus] = {
    OrderStatus.PENDING,
    OrderStatus.PAYMENT_PROCESSING,
    OrderStatus.CONFIRMED,
}


def assert_transition(current: OrderStatus, target: OrderStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvariantViolationError(
            "illegal_order_transition",
            metadata={"from": current.value, "to": target.value},
        )
