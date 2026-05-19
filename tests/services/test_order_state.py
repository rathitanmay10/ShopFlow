import pytest

from app.core.exceptions import InvariantViolationError
from app.models.order import OrderStatus
from app.services.order_state import ALLOWED_TRANSITIONS, CANCELLABLE, assert_transition


def test_pending_can_go_to_payment_processing() -> None:
    assert_transition(OrderStatus.PENDING, OrderStatus.PAYMENT_PROCESSING)


def test_shipped_cannot_be_cancelled() -> None:
    with pytest.raises(InvariantViolationError):
        assert_transition(OrderStatus.SHIPPED, OrderStatus.CANCELLED)


def test_delivered_is_terminal() -> None:
    assert ALLOWED_TRANSITIONS[OrderStatus.DELIVERED] == set()


def test_cancellable_set_excludes_post_ship_states() -> None:
    assert OrderStatus.SHIPPED not in CANCELLABLE
    assert OrderStatus.DELIVERED not in CANCELLABLE
    assert OrderStatus.PENDING in CANCELLABLE
    assert OrderStatus.PAYMENT_PROCESSING in CANCELLABLE
    assert OrderStatus.CONFIRMED in CANCELLABLE


def test_invalid_transition_includes_metadata() -> None:
    with pytest.raises(InvariantViolationError) as exc:
        assert_transition(OrderStatus.DELIVERED, OrderStatus.PENDING)
    assert exc.value.metadata.get("from") == "delivered"
    assert exc.value.metadata.get("to") == "pending"
