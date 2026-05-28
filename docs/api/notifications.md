# Notification endpoints

## `GET /api/v1/notifications`

Any authenticated user. Query: `page`, `page_size`. Returns notifications scoped to the caller's `user_id` — no cross-user reads.

```json
{
  "items": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "channel": "email",
      "event_type": "order_confirmed",
      "status": "sent",
      "payload": {"order_id": "...", "total": "19.98"},
      "created_at": "..."
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

## How notifications are produced

Dispatched via a single ARQ task — `send_notification(user_id, channel, event_type, payload)` — with `channel ∈ {email, sms, in_app}`.

| Event | Enqueued by | Channel |
|---|---|---|
| `order_confirmed` | `PaymentService.process` on success | `email` |
| `payment_failed` | `PaymentService.process` on terminal failure | `email` |
| `low_stock` | (not yet wired — currently logger-only) | — |

Delivery is **simulated**: each row goes into `notifications` and is marked `sent`. No real email / SMS / push provider integration.
