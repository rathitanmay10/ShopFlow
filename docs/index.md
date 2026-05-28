# ShopFlow

Event-driven e-commerce backend. Fully-async FastAPI + PostgreSQL + Redis + ARQ workers.

**Source:** <https://github.com/rathitanmay10/ShopFlow>

## What's inside

Products, inventory, orders, payments, notifications, audit logs. RBAC (customer / seller / admin) over JWT. Atomic stock decrement under concurrency. Order finite-state machine. Background workers for simulated payments and notifications.

## Stack

- Python 3.13, FastAPI, Pydantic v2
- SQLAlchemy 2.x async (`asyncpg`), Alembic
- Redis + ARQ (background tasks)
- JWT auth (bcrypt password hashing)
- Tooling: `uv`, `ruff`, `ty`, `pytest`, `pre-commit`

## Where to go

- New here → [Getting started](getting-started.md)
- Big picture → [Architecture](architecture.md)
- Rules of the road → [Conventions](conventions.md)
- HTTP surface → [API overview](api/overview.md)
- Domain rules → [Inventory](concepts/inventory.md), [Order lifecycle](concepts/order-lifecycle.md), [Payments](concepts/payments.md), [Auth](concepts/auth.md)
- Running it → [Workers](operations/workers.md), [Migrations](operations/migrations.md), [Testing](operations/testing.md)
