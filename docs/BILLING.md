# Paperlight billing and entitlement runbook

## Scope

The billing layer is deliberately split into two systems:

- Stripe owns Checkout, payment methods, invoices, renewals, retries, cancellation and the hosted Customer Portal.
- Paperlight owns `Plan`, `Entitlement`, `Quota`, `Usage` and the final decision to grant product access.

Core document code never checks `isPro`. It calls the centralized catalog and quota service. The current identity boundary is still the configured owner account; public registration, account recovery and multi-user rollout are separate release gates.

## Modes

| `BILLING_MODE` | Behaviour | Production allowed |
|---|---|---|
| `disabled` | Keeps the existing owner-only deployment working. `BILLING_DISABLED_PLAN` selects the owner plan and quota enforcement is off. Usage is still visible. | Yes; current default |
| `test` | Enables an authenticated fake Checkout and explicit Free/Pro switching. No external payment request is made. | No |
| `stripe` | Enables Stripe-hosted subscription Checkout, Customer Portal and signed webhooks. | Yes, after all required configuration and operational gates pass |

## Central plan catalog

`services/api/app/billing_catalog.py` is the only product-plan definition. Defaults are configurable without changing business routes:

| Meter | Free | Pro | Environment variables |
|---|---:|---:|---|
| Active documents | 3 | 25 | `BILLING_FREE_DOCUMENTS`, `BILLING_PRO_DOCUMENTS` |
| Current document storage | 10 MiB | 250 MiB | `BILLING_FREE_STORAGE_BYTES`, `BILLING_PRO_STORAGE_BYTES` |
| AI risk detections per calendar month | 2 | 20 | `BILLING_FREE_DETECTION_RUNS`, `BILLING_PRO_DETECTION_RUNS` |
| Agent rewrites per calendar month | 5 | 60 | `BILLING_FREE_REWRITE_RUNS`, `BILLING_PRO_REWRITE_RUNS` |

These defaults are conservative product assumptions, not validated unit economics. Reconcile Pangram and DeepSeek costs before setting the live Price or increasing quotas. System-wide Provider safety limits remain independent and can stop a paid call before the customer quota is exhausted.

Billable storage means the current document text plus the original uploaded DOCX. Immutable system-created history is excluded from the customer-facing storage meter. Existing documents are backfilled with current text bytes at startup; historical original DOCX byte sizes are not guessed.

## API contract

| Endpoint | Authentication | Purpose |
|---|---|---|
| `GET /api/v1/billing/summary` | Bearer session | Current plan, entitlements, subscription state, usage and plan catalog |
| `POST /api/v1/billing/events` | Bearer session | Low-cardinality Pro-page and upgrade-funnel events |
| `POST /api/v1/billing/checkout-session` | Bearer session | Stripe-hosted recurring Checkout or fake test upgrade |
| `POST /api/v1/billing/portal-session` | Bearer session | Stripe-hosted subscription management |
| `POST /api/v1/billing/test/plan` | Bearer session; test mode only | Deterministic Free/Pro transition testing |
| `POST /api/v1/billing/webhook` | Stripe signature | Idempotent asynchronous subscription reconciliation |

Quota exhaustion returns HTTP `402` with `detail.code=quota_exceeded`, the affected meter, current usage and limit. Only that resource is blocked; login, reading, editing, export, deletion and other non-exhausted core capabilities remain available.

Detection and rewrite requests must include a fresh `Idempotency-Key` (16–128 URL-safe characters) whenever billing is enabled. A replay of a consumed or still-reserved key returns `409 duplicate_request`; it is never counted as a new customer attempt. The browser creates a new random key only when the owner explicitly starts a new operation.

Queued analysis reservations transition `reserved → queued → running → consumed/released` and are bound to the job ID. Only unqueued reservations may expire by age; a worker must atomically claim the matching queued reservation before calling a Provider. This prevents a delayed Celery job from running after its quota unit has disappeared.

## Stripe setup

1. Create one Product for Paperlight Pro and one recurring monthly Price. Do not use the deprecated Stripe `plan` object.
2. Configure the Customer Portal for payment-method updates and cancellation. Cancellation at period end remains Pro while Stripe reports the subscription as active.
3. Register `https://<api-host>/api/v1/billing/webhook` with Stripe API version `2026-02-25.clover` and subscribe to:
   - `checkout.session.completed`
   - `checkout.session.expired`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.paid`
   - `invoice.payment_failed`
4. Set server-only variables:
   - `BILLING_MODE=stripe`
   - `BILLING_APP_URL=https://<frontend-host>/<base-path>`
   - `STRIPE_SECRET_KEY=<restricted or secret server key>`
   - `STRIPE_WEBHOOK_SECRET=<endpoint signing secret>`
   - `STRIPE_PRO_MONTHLY_PRICE_ID=price_...`
   Production accepts only live-mode server keys and signed events with `livemode=true`. Test-mode credentials belong only in a non-production environment. Before launch, verify in Stripe that the configured recurring Price and Customer Portal configuration are also live-mode objects.
5. Keep dynamic payment methods configured in Stripe. Paperlight does not send a card-only `payment_method_types` list.
6. Do not enable Stripe automatic tax until the merchant's registrations, product tax code, invoicing obligations and target jurisdictions are confirmed. This implementation does not imply tax compliance.

Checkout metadata contains only the random Paperlight billing-account ID and target plan. No document text, credential or session token is sent to Stripe. Webhook storage keeps the event ID, type, timestamps and payload hash, not the full payment payload.

## Access transitions

- `active` or `trialing` with the configured Pro Price grants Pro.
- Cancellation scheduled for the period end remains Pro while the subscription status is active.
- `past_due` retains Pro only for `BILLING_PAST_DUE_GRACE_DAYS`; lazy summary/quota reads downgrade after the grace deadline.
- `canceled`, `incomplete`, `incomplete_expired`, `paused`, `unpaid`, deletion, or an unrecognized Price resolves to Free.
- Older subscription events cannot overwrite a newer materialized state. Exact event replays are acknowledged; the same Stripe event ID with a changed payload is rejected.
- Invoice events are informational only. They never grant or revoke access because late invoices and invoices for another subscription can share a Customer. A price-validated, account-bound `customer.subscription.*` event is the entitlement authority.
- Checkout attempts are immutable per Stripe Session. An open unexpired hosted URL is reused, expiration creates a new attempt, late events can mutate only their exact Session, and a completed or conflicting attempt must reconcile before another subscription can be created. A validated terminal subscription event closes a completed attempt so a later resubscription can safely start.
- Same-second subscription events are ordered fail-closed by state severity: terminal state outranks past-due, which outranks active. A lower-rank event at the same timestamp cannot restore access.
- The past-due grace deadline is anchored when the account first enters `past_due`; repeated updates do not extend it.

## Conflict and recovery runbook

If the billing summary reports a reconciliation warning, keep product access at the last validated state and do not manually replay Checkout:

1. Inspect the `billing_checkout_attempts` status and matching `billing_webhook_events.error_code`; do not inspect or copy document content.
2. In Stripe, compare the Customer, subscription ID, configured Price and event timeline with the safe IDs stored on the billing account.
3. If two subscriptions exist, decide which one is authoritative, cancel/refund the duplicate according to the published policy, then replay only the signed subscription event for the retained subscription.
4. Confirm the warning clears and the plan matches the retained subscription. Record the operational decision outside application logs without secrets.

`subscription_conflict`, `subscription_mismatch`, and `subscription_binding_mismatch` are fail-closed states. They are intentionally not resolved by invoice events.

## Database migrations

The API runs `alembic upgrade head` at startup and holds a PostgreSQL transaction-scoped advisory lock so replicas cannot migrate concurrently. For an existing Paperlight database, the adoption revision creates only missing billing tables and records the schema revision; it does not clear documents or history. A dedicated one-off migration job remains preferable when the deployment platform supports it. Before deployment, take the normal PostgreSQL backup and run:

```powershell
python -m services.api.app.migration_runner upgrade
```

Rollback of the initial billing revision removes billing-only tables and therefore their quota/webhook history; it does not remove Paperlight documents. Use it only while `BILLING_MODE=disabled`, after a backup:

```powershell
python -m services.api.app.migration_runner downgrade base
```

## Verification and launch gates

Before changing production from `disabled` to `stripe`:

1. Run the full backend, frontend, type-check, build, OpenAPI and static-secret suites.
2. Use Stripe test mode and Stripe CLI forwarding to verify initial payment, duplicate webhook delivery, renewal, failed payment, recovery, cancellation at period end and immediate deletion.
3. Confirm the configured Price is the only Price that grants Pro.
4. Confirm the Customer Portal, support contact, cancellation wording, refund policy, privacy notice, terms, invoices/receipts and tax treatment.
5. Reconcile Paperlight quota events against Stripe test invoices and Provider usage.
6. Complete multi-user identity, verified email/recovery, distributed abuse controls and tenant isolation before public/student rollout.

The current code is a deployable billing foundation and complete fake-payment acceptance path. It must not be described as a public commercial launch while the identity, refund/support and jurisdiction-specific compliance gates remain open.
