import logging
import secrets
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import InvariantViolationError, NotFoundError
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentEvent, PaymentStatus
from app.services.order_state import assert_transition
from app.workers.queue import enqueue

logger = logging.getLogger(__name__)


class PaymentSimulationError(Exception):
    """Raised by the simulator to trigger ARQ retry."""


class PaymentService:
    """Simulated payment gateway.

    On `process`, advances payment state machine. Random outcome controlled by
    `settings.payment_success_rate`. Persists a `PaymentEvent` for every transition.
    Raises `PaymentSimulationError` on failure so ARQ retries the task.
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def get_or_create_for_order(self, order: Order) -> Payment:
        existing = (
            await self.session.execute(select(Payment).where(Payment.order_id == order.id))
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        payment = Payment(order_id=order.id, amount=order.total, status=PaymentStatus.INITIATED)
        self.session.add(payment)
        await self.session.flush()
        self._record_event(payment, None, PaymentStatus.INITIATED, "created")
        return payment

    async def process(self, order_id: UUID) -> Payment:
        order = await self.session.get(Order, order_id)
        if order is None:
            raise NotFoundError("order_not_found")
        if order.status != OrderStatus.PAYMENT_PROCESSING:
            raise InvariantViolationError(
                "order_not_in_payment_processing",
                metadata={"status": order.status.value},
            )

        payment = await self.get_or_create_for_order(order)
        payment.attempts += 1

        self._transition(payment, PaymentStatus.PROCESSING, "attempt_started")

        if secrets.randbelow(1000) < int(self.settings.payment_success_rate * 1000):
            payment.external_txn_id = uuid4().hex
            self._transition(payment, PaymentStatus.SUCCESS, "simulated_success")
            assert_transition(order.status, OrderStatus.CONFIRMED)
            order.status = OrderStatus.CONFIRMED
            await enqueue(
                self.settings,
                "send_email",
                str(order.customer_id),
                "order_confirmed",
                {"order_id": str(order.id), "total": str(order.total)},
            )
            return payment

        self._transition(payment, PaymentStatus.FAILED, "simulated_failure")
        # Roll back to PENDING so a retry attempt can re-enter PAYMENT_PROCESSING.
        order.status = OrderStatus.PENDING
        await enqueue(
            self.settings,
            "send_email",
            str(order.customer_id),
            "payment_failed",
            {"order_id": str(order.id), "attempt": payment.attempts},
        )
        raise PaymentSimulationError("payment_simulated_failure")

    def _transition(self, payment: Payment, to: PaymentStatus, reason: str) -> None:
        self._record_event(payment, payment.status, to, reason)
        payment.status = to

    def _record_event(
        self,
        payment: Payment,
        from_status: PaymentStatus | None,
        to_status: PaymentStatus,
        reason: str,
    ) -> None:
        self.session.add(
            PaymentEvent(
                payment_id=payment.id,
                from_status=from_status,
                to_status=to_status,
                reason=reason,
            )
        )
