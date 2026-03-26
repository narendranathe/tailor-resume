"""
app/routes/billing.py
Stripe billing endpoints — checkout session creation and webhook handling.

POST /billing/checkout  — creates Stripe Checkout session (Pro $9/mo), returns {checkout_url}
POST /billing/webhook   — handles checkout.session.completed / customer.subscription.deleted
GET  /usage             — returns {plan, count_this_month, limit} for authenticated user
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.auth import get_current_user
from app.config import settings
from app.middleware.usage import get_usage_info, set_user_plan

router = APIRouter(tags=["billing"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CheckoutResponse(BaseModel):
    checkout_url: str


class UsageResponse(BaseModel):
    plan: str
    count_this_month: int
    limit: int | None  # None = unlimited (pro)


# ---------------------------------------------------------------------------
# GET /usage
# ---------------------------------------------------------------------------

@router.get("/usage", response_model=UsageResponse)
async def get_usage(user_id: str = Depends(get_current_user)):
    """Return current plan and usage for the authenticated user."""
    info = get_usage_info(user_id)
    return UsageResponse(**info)


# ---------------------------------------------------------------------------
# POST /billing/checkout
# ---------------------------------------------------------------------------

@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    request: Request,
    user_id: str = Depends(get_current_user),
):
    """
    Create a Stripe Checkout session for the Pro plan ($9/mo).
    Returns {checkout_url} that the client should redirect to.
    """
    if not settings.has_stripe:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured on this server.",
        )

    import stripe  # lazy import — only needed when Stripe is configured

    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Determine the origin for success/cancel URLs
    origin = str(request.base_url).rstrip("/")
    success_url = f"{origin}/?checkout=success"
    cancel_url = f"{origin}/?checkout=cancel"

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": settings.STRIPE_PRO_PRICE_ID, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=user_id,
        metadata={"user_id": user_id},
    )

    return CheckoutResponse(checkout_url=session.url)


# ---------------------------------------------------------------------------
# POST /billing/webhook
# ---------------------------------------------------------------------------

@router.post("/billing/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
):
    """
    Handle Stripe webhook events.

    Events handled:
      - checkout.session.completed  → set plan=pro
      - customer.subscription.deleted → revert plan=free

    IMPORTANT: raw bytes are used for signature validation — do NOT parse body as JSON first.
    """
    if not settings.has_stripe:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured on this server.",
        )

    import stripe  # lazy import

    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Must read raw bytes before any JSON parsing for HMAC signature to validate
    raw_body = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload=raw_body,
            sig_header=stripe_signature or "",
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid webhook signature: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Webhook parse error: {exc}",
        ) from exc

    event_type: str = event["type"]

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        user_id: str = session.get("metadata", {}).get("user_id") or session.get("client_reference_id", "")
        stripe_customer_id: str = session.get("customer", "")
        if user_id:
            set_user_plan(user_id, "pro", stripe_customer_id=stripe_customer_id or None)

    elif event_type == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        stripe_customer_id = subscription.get("customer", "")
        # Look up user by stripe_customer_id and revert to free
        # For Supabase: query user_profiles; for SQLite: query user_plans
        if stripe_customer_id:
            _revert_plan_by_customer(stripe_customer_id)

    # Return 200 for all other event types (Stripe requires a 2xx response)
    return {"received": True}


def _revert_plan_by_customer(stripe_customer_id: str) -> None:
    """Find the user associated with stripe_customer_id and set plan=free."""
    if settings.has_supabase:
        try:
            from supabase import create_client  # type: ignore
            client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
            resp = (
                client.table("user_profiles")
                .select("user_id")
                .eq("stripe_customer_id", stripe_customer_id)
                .maybe_single()
                .execute()
            )
            if resp.data:
                user_id = resp.data["user_id"]
                set_user_plan(user_id, "free")
        except Exception:
            pass  # Best-effort; log in production
    else:
        import sqlite3
        from pathlib import Path
        db_path = Path("~/.tailor_resume/usage.db").expanduser()
        if not db_path.exists():
            return
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT user_id FROM user_plans WHERE stripe_customer_id=?", (stripe_customer_id,)
        ).fetchone()
        if row:
            set_user_plan(row[0], "free")
        conn.close()
