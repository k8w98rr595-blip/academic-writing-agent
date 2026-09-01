from __future__ import annotations

import json
import sys
import types
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.api.app import billing, billing_catalog
from services.api.app.billing import (
    billing_summary,
    create_checkout_session,
    ensure_billing_account,
    finalize_product_usage,
    process_stripe_event,
    claim_product_usage,
    queue_product_usage,
    reserve_product_usage,
    verify_stripe_event,
)
from services.api.app.billing_catalog import METER_DETECTION
from services.api.app.database import session_scope
from services.api.app.models import BillingAccount, BillingCheckoutAttempt, BillingProductEvent, BillingWebhookEvent, ProductUsageReservation


def use_billing_settings(monkeypatch: pytest.MonkeyPatch, **changes):
    configured = replace(billing.get_settings(), **changes)
    monkeypatch.setattr(billing, "get_settings", lambda: configured)
    monkeypatch.setattr(billing_catalog, "get_settings", lambda: configured)
    return configured


def paid_headers(headers: dict[str, str], key: str) -> dict[str, str]:
    return {**headers, "Idempotency-Key": key}


def test_installed_stripe_sdk_exposes_required_v15_client_surface():
    import stripe
    from stripe import StripeClient

    assert stripe.VERSION == "15.6.0"
    client = StripeClient("sk_test_placeholder")
    assert callable(client.v1.checkout.sessions.create)
    assert callable(client.v1.billing_portal.sessions.create)
    assert callable(client.v1.subscriptions.retrieve)


def test_production_rejects_non_live_stripe_events(monkeypatch):
    use_billing_settings(monkeypatch, app_env="production", billing_mode="stripe")
    event = {"id": "evt_test_mode", "type": "invoice.paid", "livemode": False, "data": {"object": {}}}
    with session_scope() as db, pytest.raises(HTTPException) as raised:
        process_stripe_event(db, event, json.dumps(event).encode())
    assert raised.value.status_code == 400


def test_billing_summary_is_authenticated_and_keeps_core_features(client, headers):
    assert client.get("/api/v1/billing/summary").status_code == 401
    response = client.get("/api/v1/billing/summary", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["key"] == "pro"
    assert payload["plan"]["entitlements"]["core_workspace"] is True
    assert payload["plan"]["entitlements"]["ai_detection"] is True
    assert payload["checkoutAvailable"] is False
    assert "storage_bytes" in payload["usage"]


def test_test_mode_supports_complete_upgrade_and_downgrade_flow(client, headers, monkeypatch):
    use_billing_settings(monkeypatch, billing_mode="test", billing_disabled_plan="free")

    before = client.get("/api/v1/billing/summary", headers=headers).json()
    assert before["plan"]["key"] == "free"
    upgraded = client.post(
        "/api/v1/billing/checkout-session",
        headers=headers,
        json={"trigger": "test_suite"},
    )
    assert upgraded.status_code == 200
    assert upgraded.json()["url"].endswith("/?billing=test-success")
    after = client.get("/api/v1/billing/summary", headers=headers).json()
    assert after["plan"]["key"] == "pro"
    assert after["subscription"]["status"] == "active"
    assert after["funnel"]["upgrade_clicked"] == 1
    assert after["funnel"]["checkout_started"] == 1

    downgraded = client.post(
        "/api/v1/billing/test/plan",
        headers=headers,
        json={"plan": "free"},
    )
    assert downgraded.status_code == 204
    assert client.get("/api/v1/billing/summary", headers=headers).json()["plan"]["key"] == "free"


def test_product_quota_is_idempotent_and_only_counts_consumed_or_reserved(monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="test",
        billing_disabled_plan="free",
        billing_free_detection_runs=1,
    )
    owner = "quota@example.com"

    first = reserve_product_usage(owner, METER_DETECTION, "same-operation")
    with pytest.raises(HTTPException) as in_progress:
        reserve_product_usage(owner, METER_DETECTION, "same-operation")
    assert in_progress.value.status_code == 409
    finalize_product_usage(first, consumed=True)
    with pytest.raises(HTTPException) as duplicate:
        reserve_product_usage(owner, METER_DETECTION, "same-operation")
    assert duplicate.value.status_code == 409
    assert duplicate.value.detail["code"] == "duplicate_request"

    with pytest.raises(HTTPException) as raised:
        reserve_product_usage(owner, METER_DETECTION, "second-operation")
    assert raised.value.status_code == 402
    assert raised.value.detail["code"] == "quota_exceeded"

    with session_scope() as db:
        rows = list(db.query(ProductUsageReservation).filter_by(owner_email=owner))
        events = list(db.query(BillingProductEvent).filter_by(owner_email=owner, event_name="limit_hit"))
        assert len(rows) == 1
        assert rows[0].status == "consumed"
        assert len(events) == 1


def test_queued_product_quota_does_not_age_out_before_worker_claim(monkeypatch):
    use_billing_settings(monkeypatch, billing_mode="test", billing_disabled_plan="free")
    reservation_id = reserve_product_usage("queued@example.com", METER_DETECTION, "queued-operation-0001")
    with session_scope() as db:
        queue_product_usage(reservation_id, "job_queued", db)
        reservation = db.get(ProductUsageReservation, reservation_id)
        reservation.created_at = billing.utcnow() - billing.timedelta(hours=2)
    with session_scope() as db:
        summary = billing_summary(db, "queued@example.com")
        reservation = db.get(ProductUsageReservation, reservation_id)
        assert summary["usage"][METER_DETECTION]["used"] == 1
        assert reservation.status == "queued"
        assert claim_product_usage(reservation_id, "job_queued", db) is True
        assert claim_product_usage(reservation_id, "job_queued", db) is False
        finalize_product_usage(reservation_id, consumed=True, db=db)


def test_detection_endpoint_blocks_only_exhausted_meter(client, headers, coursework_text, monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="test",
        billing_disabled_plan="free",
        billing_free_detection_runs=1,
    )
    created = client.post(
        "/api/v1/documents",
        headers=headers,
        data={"title": "Quota boundary", "text": coursework_text},
    )
    assert created.status_code == 201
    document_id = created.json()["document"]["id"]
    first = client.post(
        f"/api/v1/documents/{document_id}/analyses",
        headers=paid_headers(headers, "billing-test-analysis-0001"),
    )
    assert first.status_code == 201
    current = client.get(f"/api/v1/documents/{document_id}", headers=headers).json()["document"]
    updated = client.patch(
        f"/api/v1/documents/{document_id}",
        headers=headers,
        json={
            "base_version_id": current["currentVersion"]["id"],
            "paragraphs": current["currentVersion"]["paragraphs"],
        },
    )
    assert updated.status_code == 200
    blocked = client.post(
        f"/api/v1/documents/{document_id}/analyses",
        headers=paid_headers(headers, "billing-test-analysis-0002"),
    )
    assert blocked.status_code == 402
    assert blocked.json()["detail"]["code"] == "quota_exceeded"
    assert blocked.json()["detail"]["meter"] == METER_DETECTION
    assert client.get(f"/api/v1/documents/{document_id}", headers=headers).status_code == 200


def test_paid_product_endpoint_requires_an_explicit_idempotency_key(client, headers, coursework_text, monkeypatch):
    use_billing_settings(monkeypatch, billing_mode="test", billing_disabled_plan="free")
    created = client.post(
        "/api/v1/documents",
        headers=headers,
        data={"title": "Idempotency boundary", "text": coursework_text},
    )
    document_id = created.json()["document"]["id"]

    response = client.post(f"/api/v1/documents/{document_id}/analyses", headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Idempotency-Key is required"


def test_stripe_subscription_webhooks_are_price_gated_replay_safe_and_ordered(monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="stripe",
        stripe_secret_key="stripe-test-key",
        stripe_webhook_secret="stripe-webhook-secret",
        stripe_pro_monthly_price_id="price_pro_monthly",
    )
    owner = "stripe@example.com"
    with session_scope() as db:
        account_id = ensure_billing_account(db, owner).id

    active_event = {
        "id": "evt_active",
        "type": "customer.subscription.created",
        "created": 2_000_000_000,
        "data": {
            "object": {
                "id": "sub_123",
                "object": "subscription",
                "customer": "cus_123",
                "status": "active",
                "cancel_at_period_end": False,
                "current_period_end": 2_000_086_400,
                "metadata": {"billing_account_id": account_id},
                "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
            }
        },
    }
    active_payload = json.dumps(active_event, sort_keys=True).encode()
    with session_scope() as db:
        assert process_stripe_event(db, active_event, active_payload) == "processed"
    with session_scope() as db:
        summary = billing_summary(db, owner)
        assert summary["plan"]["key"] == "pro"
        assert summary["subscription"]["status"] == "active"

    with session_scope() as db:
        assert process_stripe_event(db, active_event, active_payload) == "duplicate"

    stale_deleted = {
        **active_event,
        "id": "evt_stale_deleted",
        "type": "customer.subscription.deleted",
        "created": 1_999_999_999,
    }
    with session_scope() as db:
        assert process_stripe_event(db, stale_deleted, json.dumps(stale_deleted, sort_keys=True).encode()) == "stale"
    with session_scope() as db:
        assert billing_summary(db, owner)["plan"]["key"] == "pro"

    failed_invoice = {
        "id": "evt_invoice_failed",
        "type": "invoice.payment_failed",
        "created": 2_000_000_001,
        "data": {"object": {"object": "invoice", "customer": "cus_123", "subscription": "sub_123"}},
    }
    with session_scope() as db:
        assert process_stripe_event(db, failed_invoice, json.dumps(failed_invoice, sort_keys=True).encode()) == "processed"
    with session_scope() as db:
        summary = billing_summary(db, owner)
        assert summary["plan"]["key"] == "pro"
        assert summary["subscription"]["status"] == "active"

    past_due = json.loads(json.dumps(active_event))
    past_due["id"] = "evt_subscription_past_due"
    past_due["type"] = "customer.subscription.updated"
    past_due["created"] = 2_000_000_002
    past_due["data"]["object"]["status"] = "past_due"
    with session_scope() as db:
        assert process_stripe_event(db, past_due, json.dumps(past_due, sort_keys=True).encode()) == "processed"
    with session_scope() as db:
        summary = billing_summary(db, owner)
        assert summary["plan"]["key"] == "pro"
        assert summary["subscription"]["status"] == "past_due"
        assert summary["subscription"]["graceUntil"] is not None

    paid_invoice = {
        **failed_invoice,
        "id": "evt_invoice_paid",
        "type": "invoice.paid",
        "created": 2_000_000_003,
    }
    with session_scope() as db:
        assert process_stripe_event(db, paid_invoice, json.dumps(paid_invoice, sort_keys=True).encode()) == "processed"
    with session_scope() as db:
        summary = billing_summary(db, owner)
        assert summary["plan"]["key"] == "pro"
        assert summary["subscription"]["status"] == "past_due"

    recovered = json.loads(json.dumps(active_event))
    recovered["id"] = "evt_subscription_recovered"
    recovered["type"] = "customer.subscription.updated"
    recovered["created"] = 2_000_000_004
    with session_scope() as db:
        assert process_stripe_event(db, recovered, json.dumps(recovered, sort_keys=True).encode()) == "processed"
    with session_scope() as db:
        summary = billing_summary(db, owner)
        assert summary["plan"]["key"] == "pro"
        assert summary["subscription"]["status"] == "active"
        assert summary["subscription"]["graceUntil"] is None

    wrong_price = json.loads(json.dumps(active_event))
    wrong_price["id"] = "evt_wrong_price"
    wrong_price["type"] = "customer.subscription.updated"
    wrong_price["created"] = 2_000_000_005
    wrong_price["data"]["object"]["items"]["data"][0]["price"]["id"] = "price_untrusted"
    with session_scope() as db:
        assert process_stripe_event(db, wrong_price, json.dumps(wrong_price, sort_keys=True).encode()) == "processed"
    with session_scope() as db:
        summary = billing_summary(db, owner)
        assert summary["plan"]["key"] == "free"
        assert db.query(BillingWebhookEvent).count() == 7


def test_equal_second_terminal_subscription_event_cannot_be_reversed(monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="stripe",
        stripe_secret_key="stripe-test-key",
        stripe_webhook_secret="stripe-webhook-secret",
        stripe_pro_monthly_price_id="price_pro_monthly",
    )
    owner = "same-second@example.com"
    with session_scope() as db:
        account_id = ensure_billing_account(db, owner).id
    base = {
        "id": "evt_same_active",
        "type": "customer.subscription.created",
        "created": 2_100_000_000,
        "data": {"object": {
            "id": "sub_same",
            "object": "subscription",
            "customer": "cus_same",
            "status": "active",
            "metadata": {"billing_account_id": account_id},
            "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
        }},
    }
    deleted = json.loads(json.dumps(base))
    deleted.update(id="evt_same_deleted", type="customer.subscription.deleted")
    deleted["data"]["object"]["status"] = "canceled"
    late_active = json.loads(json.dumps(base))
    late_active.update(id="evt_same_late_active", type="customer.subscription.updated")
    with session_scope() as db:
        assert process_stripe_event(db, base, json.dumps(base, sort_keys=True).encode()) == "processed"
        assert process_stripe_event(db, deleted, json.dumps(deleted, sort_keys=True).encode()) == "processed"
        assert process_stripe_event(db, late_active, json.dumps(late_active, sort_keys=True).encode()) == "stale"
    with session_scope() as db:
        assert billing_summary(db, owner)["plan"]["key"] == "free"


def test_subscription_customer_binding_is_immutable_and_grace_is_not_extended(monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="stripe",
        stripe_secret_key="stripe-test-key",
        stripe_webhook_secret="stripe-webhook-secret",
        stripe_pro_monthly_price_id="price_pro_monthly",
    )
    owner = "customer-bound@example.com"
    with session_scope() as db:
        account_id = ensure_billing_account(db, owner).id
    active = {
        "id": "evt_bound_active",
        "type": "customer.subscription.created",
        "created": 2_100_000_000,
        "data": {"object": {
            "id": "sub_bound",
            "object": "subscription",
            "customer": "cus_bound",
            "status": "active",
            "metadata": {"billing_account_id": account_id},
            "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
        }},
    }
    past_due = json.loads(json.dumps(active))
    past_due.update(id="evt_bound_due", type="customer.subscription.updated", created=2_100_000_001)
    past_due["data"]["object"]["status"] = "past_due"
    repeated_due = json.loads(json.dumps(past_due))
    repeated_due.update(id="evt_bound_due_again", created=2_100_000_002)
    wrong_customer = json.loads(json.dumps(active))
    wrong_customer.update(id="evt_wrong_customer", type="customer.subscription.updated", created=2_100_000_003)
    wrong_customer["data"]["object"]["id"] = "sub_replacement"
    wrong_customer["data"]["object"]["customer"] = "cus_other"
    with session_scope() as db:
        process_stripe_event(db, active, json.dumps(active, sort_keys=True).encode())
        process_stripe_event(db, past_due, json.dumps(past_due, sort_keys=True).encode())
        first_grace = db.query(BillingAccount).filter_by(owner_email=owner).one().grace_until
        process_stripe_event(db, repeated_due, json.dumps(repeated_due, sort_keys=True).encode())
        assert db.query(BillingAccount).filter_by(owner_email=owner).one().grace_until == first_grace
        assert process_stripe_event(db, wrong_customer, json.dumps(wrong_customer, sort_keys=True).encode()) == "subscription_mismatch"
    with session_scope() as db:
        account = db.query(BillingAccount).filter_by(owner_email=owner).one()
        assert account.provider_customer_id == "cus_bound"
        assert account.provider_subscription_id == "sub_bound"


def test_invoice_cannot_restore_deleted_or_unrelated_subscription(monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="stripe",
        stripe_secret_key="stripe-test-key",
        stripe_webhook_secret="stripe-webhook-secret",
        stripe_pro_monthly_price_id="price_pro_monthly",
    )
    owner = "deleted@example.com"
    with session_scope() as db:
        account_id = ensure_billing_account(db, owner).id
    subscription = {
        "id": "evt_sub_active",
        "type": "customer.subscription.created",
        "created": 2_100_000_000,
        "data": {"object": {
            "id": "sub_current",
            "object": "subscription",
            "customer": "cus_current",
            "status": "active",
            "metadata": {"billing_account_id": account_id},
            "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
        }},
    }
    with session_scope() as db:
        process_stripe_event(db, subscription, json.dumps(subscription, sort_keys=True).encode())
    deleted = json.loads(json.dumps(subscription))
    deleted["id"] = "evt_sub_deleted"
    deleted["type"] = "customer.subscription.deleted"
    deleted["created"] = 2_100_000_001
    deleted["data"]["object"]["status"] = "canceled"
    with session_scope() as db:
        process_stripe_event(db, deleted, json.dumps(deleted, sort_keys=True).encode())
    late_invoice = {
        "id": "evt_late_invoice",
        "type": "invoice.paid",
        "created": 2_100_000_002,
        "data": {"object": {"object": "invoice", "customer": "cus_current", "subscription": "sub_current"}},
    }
    unrelated_invoice = {
        **late_invoice,
        "id": "evt_unrelated_invoice",
        "created": 2_100_000_003,
        "data": {"object": {"object": "invoice", "customer": "cus_current", "subscription": "sub_other"}},
    }
    with session_scope() as db:
        process_stripe_event(db, late_invoice, json.dumps(late_invoice, sort_keys=True).encode())
        process_stripe_event(db, unrelated_invoice, json.dumps(unrelated_invoice, sort_keys=True).encode())
    with session_scope() as db:
        summary = billing_summary(db, owner)
        assert summary["plan"]["key"] == "free"
        assert summary["subscription"]["status"] == "canceled"


def test_unbound_subscription_event_cannot_claim_an_account_by_customer_id(monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="stripe",
        stripe_secret_key="stripe-test-key",
        stripe_webhook_secret="stripe-webhook-secret",
        stripe_pro_monthly_price_id="price_pro_monthly",
    )
    owner = "binding@example.com"
    with session_scope() as db:
        account = ensure_billing_account(db, owner)
        account.provider_customer_id = "cus_shared"
        account.provider = "stripe"
        db.commit()

    event = {
        "id": "evt_unbound_subscription",
        "type": "customer.subscription.created",
        "created": 2_100_000_000,
        "data": {"object": {
            "id": "sub_unbound",
            "object": "subscription",
            "customer": "cus_shared",
            "status": "active",
            "metadata": {},
            "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
        }},
    }
    with session_scope() as db:
        outcome = process_stripe_event(db, event, json.dumps(event, sort_keys=True).encode())
    assert outcome == "subscription_mismatch"
    with session_scope() as db:
        summary = billing_summary(db, owner)
        ledger = db.query(BillingWebhookEvent).filter_by(provider_event_id=event["id"]).one()
        account = db.query(BillingAccount).filter_by(owner_email=owner).one()
        conflicts = db.query(BillingProductEvent).filter_by(owner_email=owner, event_name="billing_conflict").all()
        assert summary["plan"]["key"] == "free"
        assert account.provider_subscription_id is None
        assert ledger.error_code == "subscription_binding_mismatch"
        assert len(conflicts) == 1


def test_duplicate_checkout_subscription_is_fail_closed_and_visible(monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="stripe",
        stripe_secret_key="stripe-test-key",
        stripe_webhook_secret="stripe-webhook-secret",
        stripe_pro_monthly_price_id="price_pro_monthly",
    )
    owner = "conflict@example.com"
    with session_scope() as db:
        account = ensure_billing_account(db, owner)
        account.plan_key = "pro"
        account.plan_source = "stripe"
        account.subscription_status = "active"
        account.provider = "stripe"
        account.provider_customer_id = "cus_existing"
        account.provider_subscription_id = "sub_existing"
        attempt = BillingCheckoutAttempt(
            id="checkout_attempt_conflict",
            billing_account_id=account.id,
            attempt_token="attempt_conflict_token",
            price_id="price_pro_monthly",
            provider_session_id="cs_conflict",
            checkout_url="https://checkout.stripe.com/c/pay/conflict",
            status="open",
        )
        db.add(attempt)
        db.commit()
        account_id = account.id

    event = {
        "id": "evt_checkout_conflict",
        "type": "checkout.session.completed",
        "created": 2_100_000_000,
        "data": {"object": {
            "id": "cs_conflict",
            "object": "checkout.session",
            "customer": "cus_existing",
            "subscription": "sub_duplicate",
            "metadata": {"billing_account_id": account_id},
        }},
    }
    with session_scope() as db:
        assert process_stripe_event(db, event, json.dumps(event, sort_keys=True).encode()) == "processed"
    with session_scope() as db:
        summary = billing_summary(db, owner)
        attempt = db.query(BillingCheckoutAttempt).one()
        ledger = db.query(BillingWebhookEvent).filter_by(provider_event_id=event["id"]).one()
        account = db.query(BillingAccount).filter_by(owner_email=owner).one()
        assert summary["plan"]["key"] == "pro"
        assert account.provider_subscription_id == "sub_existing"
        assert summary["subscription"]["checkoutStatus"] == "conflict"
        assert summary["warnings"]
        assert attempt.status == "conflict"
        assert ledger.error_code == "subscription_conflict"


def test_late_checkout_event_cannot_mutate_a_newer_attempt(monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="stripe",
        stripe_secret_key="stripe-test-key",
        stripe_webhook_secret="stripe-webhook-secret",
        stripe_pro_monthly_price_id="price_pro_monthly",
    )
    owner = "late-checkout@example.com"
    with session_scope() as db:
        account = ensure_billing_account(db, owner)
        old = BillingCheckoutAttempt(
            id="checkout_attempt_old",
            billing_account_id=account.id,
            attempt_token="old_attempt_token_0001",
            price_id="price_pro_monthly",
            provider_session_id="cs_old",
            status="expired",
        )
        current = BillingCheckoutAttempt(
            id="checkout_attempt_current",
            billing_account_id=account.id,
            attempt_token="current_attempt_token_0001",
            price_id="price_pro_monthly",
            provider_session_id="cs_current",
            checkout_url="https://checkout.stripe.com/c/pay/current",
            status="open",
            created_at=billing.utcnow() + billing.timedelta(seconds=1),
        )
        db.add_all([old, current])
        db.commit()
        account_id = account.id
    event = {
        "id": "evt_late_checkout",
        "type": "checkout.session.completed",
        "created": 2_100_000_000,
        "data": {"object": {
            "id": "cs_old",
            "object": "checkout.session",
            "customer": "cus_old",
            "subscription": "sub_old",
            "metadata": {"billing_account_id": account_id},
        }},
    }
    with session_scope() as db:
        assert process_stripe_event(db, event, json.dumps(event, sort_keys=True).encode()) == "checkout_mismatch"
    with session_scope() as db:
        current = db.get(BillingCheckoutAttempt, "checkout_attempt_current")
        account = db.query(BillingAccount).filter_by(owner_email=owner).one()
        assert current.status == "open"
        assert current.provider_session_id == "cs_current"
        assert account.provider_subscription_id is None


def test_terminal_subscription_allows_a_new_immutable_checkout_attempt(monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="stripe",
        billing_app_url="https://paperlight.example/app",
        stripe_secret_key="stripe-test-key",
        stripe_webhook_secret="stripe-webhook-secret",
        stripe_pro_monthly_price_id="price_pro_monthly",
    )
    owner = "resubscribe@example.com"
    with session_scope() as db:
        account = ensure_billing_account(db, owner)
        db.add(BillingCheckoutAttempt(
            id="checkout_attempt_completed",
            billing_account_id=account.id,
            attempt_token="completed_attempt_token_0001",
            price_id="price_pro_monthly",
            provider_session_id="cs_completed",
            status="completed",
        ))
        db.commit()
        account_id = account.id
    active = {
        "id": "evt_resub_active",
        "type": "customer.subscription.created",
        "created": 2_100_000_000,
        "data": {"object": {
            "id": "sub_resub",
            "object": "subscription",
            "customer": "cus_resub",
            "status": "active",
            "metadata": {"billing_account_id": account_id},
            "items": {"data": [{"price": {"id": "price_pro_monthly"}}]},
        }},
    }
    deleted = json.loads(json.dumps(active))
    deleted.update(id="evt_resub_deleted", type="customer.subscription.deleted", created=2_100_000_001)
    deleted["data"]["object"]["status"] = "canceled"
    with session_scope() as db:
        process_stripe_event(db, active, json.dumps(active, sort_keys=True).encode())
        process_stripe_event(db, deleted, json.dumps(deleted, sort_keys=True).encode())
        assert db.get(BillingCheckoutAttempt, "checkout_attempt_completed").status == "closed"

    fake_client = SimpleNamespace(v1=SimpleNamespace(checkout=SimpleNamespace(sessions=SimpleNamespace(
        create=lambda _params, options: SimpleNamespace(
            id="cs_resubscribe",
            url="https://checkout.stripe.com/c/pay/resubscribe",
            expires_at=2_200_000_000,
        )
    ))))
    monkeypatch.setattr(billing, "_stripe_client", lambda _: fake_client)
    with session_scope() as db:
        assert create_checkout_session(db, owner, "resubscribe").endswith("/resubscribe")
    with session_scope() as db:
        attempts = db.query(BillingCheckoutAttempt).order_by(BillingCheckoutAttempt.created_at).all()
        assert len(attempts) == 2
        assert attempts[-1].status == "open"


def test_stripe_checkout_uses_hosted_subscription_price_and_opaque_account_metadata(monkeypatch):
    configured = use_billing_settings(
        monkeypatch,
        billing_mode="stripe",
        billing_app_url="https://paperlight.example/app",
        stripe_secret_key="stripe-test-key",
        stripe_webhook_secret="stripe-webhook-secret",
        stripe_pro_monthly_price_id="price_pro_monthly",
    )
    captured: dict = {}

    def create_session(params, options):
        captured["calls"] = captured.get("calls", 0) + 1
        captured["params"] = params
        captured["options"] = options
        return SimpleNamespace(
            id="cs_test_replay_safe",
            url="https://checkout.stripe.com/c/pay/test",
            expires_at=2_100_000_000,
        )

    fake_client = SimpleNamespace(
        v1=SimpleNamespace(checkout=SimpleNamespace(sessions=SimpleNamespace(create=create_session)))
    )
    monkeypatch.setattr(billing, "_stripe_client", lambda _: fake_client)
    with session_scope() as db:
        url = create_checkout_session(db, "checkout@example.com", "unit_test")
        replayed_url = create_checkout_session(db, "checkout@example.com", "unit_test")

    assert url.startswith("https://checkout.stripe.com/")
    assert replayed_url == url
    assert captured["calls"] == 1
    assert captured["params"]["mode"] == "subscription"
    assert captured["params"]["line_items"] == [{"price": configured.stripe_pro_monthly_price_id, "quantity": 1}]
    assert "payment_method_types" not in captured["params"]
    assert captured["params"]["success_url"].startswith("https://paperlight.example/app/")
    assert captured["params"]["metadata"]["billing_account_id"].startswith("billing_account_")
    assert "checkout@example.com" not in json.dumps(captured["params"]["metadata"])
    assert captured["options"]["stripe_version"] == billing.STRIPE_API_VERSION
    with session_scope() as db:
        attempt = db.query(BillingCheckoutAttempt).one()
        assert attempt.status == "open"
        assert attempt.provider_session_id == "cs_test_replay_safe"


def test_stripe_replay_with_changed_payload_is_rejected(monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="stripe",
        stripe_secret_key="stripe-test-key",
        stripe_webhook_secret="stripe-webhook-secret",
        stripe_pro_monthly_price_id="price_pro_monthly",
    )
    event = {"id": "evt_replay", "type": "invoice.paid", "created": 2_000_000_000, "data": {"object": {}}}
    with session_scope() as db:
        assert process_stripe_event(db, event, b"first") == "processed"
    with session_scope() as db, pytest.raises(HTTPException) as raised:
        process_stripe_event(db, event, b"changed")
    assert raised.value.status_code == 409


def test_webhook_verifier_uses_v15_recursive_to_dict(monkeypatch):
    use_billing_settings(
        monkeypatch,
        billing_mode="stripe",
        stripe_secret_key="stripe-test-key",
        stripe_webhook_secret="stripe-webhook-secret",
        stripe_pro_monthly_price_id="price_pro_monthly",
    )

    class SignatureVerificationError(Exception):
        pass

    class StripeObjectV15:
        def to_dict(self):
            return {"id": "evt_verified", "type": "invoice.paid", "data": {"object": {}}}

    class Webhook:
        @staticmethod
        def construct_event(payload, signature, secret, api_key):
            assert payload == b"{}"
            assert signature == "signed"
            assert secret == "stripe-webhook-secret"
            assert api_key == "stripe-test-key"
            return StripeObjectV15()

    fake_stripe = types.ModuleType("stripe")
    fake_stripe.SignatureVerificationError = SignatureVerificationError
    fake_stripe.Webhook = Webhook
    monkeypatch.setitem(sys.modules, "stripe", fake_stripe)
    assert verify_stripe_event(b"{}", "signed")["id"] == "evt_verified"
