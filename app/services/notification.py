import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationChannel, NotificationStatus

logger = logging.getLogger(__name__)


class NotificationService:
    """Records and 'delivers' notifications. Delivery is simulated — channels write
    a structured log line and mark the row as `sent`. ARQ workers wrap each call so
    the API path never blocks on simulated send."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def send(
        self,
        user_id: UUID,
        channel: NotificationChannel | str,
        event_type: str,
        payload: dict[str, Any],
    ) -> Notification:
        if isinstance(channel, str):
            channel = NotificationChannel(channel)
        notification = Notification(
            user_id=user_id,
            channel=channel,
            event_type=event_type,
            payload=payload,
            status=NotificationStatus.PENDING,
        )
        self.session.add(notification)
        await self.session.flush()
        await self._deliver(notification)
        return notification

    async def _deliver(self, notification: Notification) -> None:
        logger.info(
            "notification_sent",
            extra={
                "ctx_user_id": str(notification.user_id),
                "ctx_channel": notification.channel.value,
                "ctx_event_type": notification.event_type,
            },
        )
        notification.status = NotificationStatus.SENT
        notification.sent_at = datetime.now(UTC)
