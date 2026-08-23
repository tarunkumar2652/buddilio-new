from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import asyncio
import json
import re
from urllib.parse import quote
import jwt
import bcrypt
import bleach
import uuid
import io
import csv
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Annotated, Any, Literal

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, Query, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Header, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from pydantic import BaseModel, Field, BeforeValidator, EmailStr, ConfigDict

from emailer import send_email, wrap
from realtime import hub
from push import push_to, push_enabled, vapid_public_key
from storage import init_storage, put_object, get_object, MIME_TYPES, ALL_MIME_TYPES, DOC_MIME_TYPES, APP_NAME
from geo import COUNTRY_SEED, EXTRA_CURRENCIES, ID_DOC_TYPES
from travel import PROVIDER_ROLES, TRIP_ACTIVITIES, TRAVEL_TERMS
from invoices import invoice_pdf, template_for
import agreements as agr
import paypal
import passes
import vault
import blog
import seo
import support
import botguard
from city_guides import guide_for, auto_guide
import ai

try:
    import razorpay
except ImportError:
    razorpay = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("buddilio")

client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]

JWT_ALGORITHM = "HS256"
bearer = HTTPBearer(auto_error=False)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v))]


def clean(doc: dict) -> dict:
    if not doc:
        return doc
    out = dict(doc)
    out["id"] = str(out.pop("_id"))
    out.pop("password_hash", None)
    return out


# ---------------- auth helpers ----------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str, role: str, token_version: int = 0) -> str:
    payload = {"sub": user_id, "email": email, "role": role, "ver": int(token_version or 0),
               "exp": now_utc() + timedelta(days=7), "type": "access"}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request,
                           creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> dict:
    token = creds.credentials if creds else request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.get("status") in ("banned", "suspended"):
        raise HTTPException(status_code=403, detail=f"Your account is {user['status']}. Contact support.")
    if int(payload.get("ver") or 0) != int(user.get("token_version") or 0):
        # Password changed or access revoked since this token was issued.
        raise HTTPException(status_code=401, detail="Your session has ended. Please log in again.")
    return clean(user)


async def optional_user(request: Request,
                        creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> Optional[dict]:
    try:
        return await get_current_user(request, creds)
    except HTTPException:
        return None


def require_role(*roles):
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to do this.")
        return user
    return dep


admin_only = require_role("admin")
partner_only = require_role("partner", "admin")
manager_only = require_role("manager", "admin")


async def active_manager(user: dict = Depends(manager_only)) -> dict:
    """Managers can sign up freely but stay read-only until Buddilio approves them."""
    if user.get("role") == "manager" and user.get("status") != "active":
        raise HTTPException(status_code=403,
                            detail="Your console account is still awaiting approval from Buddilio.")
    return user


async def audit(actor: dict, action: str, entity: str, entity_id: str = "", meta: dict | None = None):
    await db.audit_logs.insert_one({
        "actor_id": actor["id"], "actor_email": actor.get("email"), "action": action,
        "entity": entity, "entity_id": entity_id, "meta": meta or {}, "created_at": iso(now_utc()),
    })


# ---------------- staff permissions ----------------
# One catalogue, one decision helper. Presets are convenience; the effective set is what is enforced.
PERMISSIONS: list[tuple[str, str, str]] = [
    ("Vendors", "vendors:view", "See vendor accounts and their stats"),
    ("Vendors", "vendors:manage", "Create, edit and suspend vendors"),
    ("Vendors", "invites:manage", "Send and revoke vendor invitations"),
    ("Vendors", "verification:manage", "Review documents and grant the verified badge"),
    ("Vendors", "agreements:manage", "Create, amend, suspend and terminate vendor agreements"),
    ("Money", "payouts:view", "See what vendors are owed"),
    ("Money", "payouts:pay", "Mark payouts as settled"),
    ("Money", "finance:view", "See orders and payments"),
    ("Money", "finance:manage", "Refunds, coupons, plans and products"),
    ("Events", "events:view", "See every event, including drafts"),
    ("Events", "events:moderate", "Approve or reject submitted events"),
    ("Members", "members:view", "See member accounts"),
    ("Members", "members:manage", "Suspend, ban or verify members"),
    ("Safety", "moderation:manage", "Moderate reviews, reports and the photo wall"),
    ("Platform", "analytics:view", "See the dashboard and reports"),
    ("Platform", "content:manage", "Edit CMS pages and platform settings"),
    ("Platform", "audit:view", "Read the audit and activity logs"),
    ("Platform", "team:manage", "Invite team members and change their permissions"),
    ("Platform", "credentials:manage", "Rotate passwords and payment/service keys"),
    ("Platform", "support:respond", "Read and reply to support chats from visitors and members"),
]
ALL_PERMISSIONS = [p[1] for p in PERMISSIONS]

STAFF_ROLES: dict[str, dict] = {
    "super_admin": {"label": "Super admin", "scope": "admin",
                    "description": "Everything, including the team itself.",
                    "permissions": ALL_PERMISSIONS},
    "operations": {"label": "Operations", "scope": "admin",
                   "description": "Vendors, invitations, verification and the event calendar.",
                   "permissions": ["vendors:view", "vendors:manage", "invites:manage", "verification:manage",
                                   "agreements:manage",
                                   "events:view", "events:moderate", "analytics:view", "audit:view",
                                   "support:respond"]},
    "finance": {"label": "Finance", "scope": "admin",
                "description": "Payouts, orders, refunds and pricing.",
                "permissions": ["payouts:view", "payouts:pay", "finance:view", "finance:manage",
                                "vendors:view", "analytics:view"]},
    "support": {"label": "Support", "scope": "admin",
                "description": "Members, reports and day-to-day moderation.",
                "permissions": ["members:view", "members:manage", "moderation:manage", "events:view",
                                "finance:view", "analytics:view", "support:respond"]},
    "moderator": {"label": "Moderator", "scope": "admin",
                  "description": "Reviews, reports and the photo wall only.",
                  "permissions": ["moderation:manage", "events:view", "members:view"]},
    "viewer": {"label": "Viewer", "scope": "admin",
               "description": "Read-only across the control centre.",
               "permissions": ["vendors:view", "payouts:view", "finance:view", "events:view",
                               "members:view", "analytics:view"]},
    "vendor_manager": {"label": "Vendor manager", "scope": "manager",
                       "description": "Console team who onboard and look after vendors.",
                       "permissions": ["vendors:view", "vendors:manage", "invites:manage", "payouts:view"]},
    "vendor_viewer": {"label": "Console viewer", "scope": "manager",
                      "description": "Console read-only — no vendor changes.",
                      "permissions": ["vendors:view", "payouts:view"]},
}
LEGACY_MANAGER_PERMS = STAFF_ROLES["vendor_manager"]["permissions"]


def perms_of(user: dict) -> set[str]:
    """Effective permissions: the preset for their staff role plus any extras granted to them."""
    role = user.get("role")
    if role not in ("admin", "manager"):
        return set()
    staff_role = user.get("staff_role")
    if not staff_role:  # accounts created before permissions existed keep what they always had
        return set(ALL_PERMISSIONS if role == "admin" else LEGACY_MANAGER_PERMS)
    preset = STAFF_ROLES.get(staff_role, {}).get("permissions", [])
    return {p for p in list(preset) + list(user.get("extra_permissions") or []) if p in ALL_PERMISSIONS}


def require_perm(*keys: str, active: bool = False):
    """Deny by default: the caller must hold at least one of the listed permissions."""
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        held = perms_of(user)
        if not held or not any(k in held for k in keys):
            raise HTTPException(status_code=403, detail="You do not have permission to do this.")
        if active and user.get("role") == "manager" and user.get("status") != "active":
            raise HTTPException(status_code=403,
                                detail="Your console account is still awaiting approval from Buddilio.")
        return user
    return dep


FRONTEND_URL = os.environ.get("FRONTEND_URL", "")

BASE_CURRENCY = os.environ.get("BASE_CURRENCY", "USD")

DEFAULT_CURRENCIES = {
    "USD": {"rate": 1.0, "symbol": "$", "label": "US Dollar", "stripe_min": 50},
    "INR": {"rate": 83.33, "symbol": "₹", "label": "Indian Rupee", "stripe_min": 4200},
    "EUR": {"rate": 0.92, "symbol": "€", "label": "Euro", "stripe_min": 50},
    "GBP": {"rate": 0.79, "symbol": "£", "label": "British Pound", "stripe_min": 30},
    "AED": {"rate": 3.67, "symbol": "AED ", "label": "UAE Dirham", "stripe_min": 200},
    "SGD": {"rate": 1.34, "symbol": "S$", "label": "Singapore Dollar", "stripe_min": 50},
    "CAD": {"rate": 1.36, "symbol": "C$", "label": "Canadian Dollar", "stripe_min": 50},
    "AUD": {"rate": 1.50, "symbol": "A$", "label": "Australian Dollar", "stripe_min": 50},
    "THB": {"rate": 32.5, "symbol": "฿", "label": "Thai Baht", "stripe_min": 1000},
    "JPY": {"rate": 150.0, "symbol": "¥", "label": "Japanese Yen", "stripe_min": 50},
    **EXTRA_CURRENCIES,
}
ZERO_DECIMAL = {"JPY", "KRW"}
# Shoppers switch between these four only; organisers can still price in their own city currency.
DISPLAY_CURRENCIES = ["USD", "INR", "GBP", "EUR"]

# Buddilio operates city by city. The live catalogue lives in db.countries so admins can add
# countries, cities and tax rules without a deploy; this in-memory copy is refreshed on every write.
COUNTRIES = [dict(c) for c in COUNTRY_SEED]
COUNTRY_BY_CODE = {c["code"]: c for c in COUNTRIES}
CITY_COUNTRY = {city: c for c in COUNTRIES for city in c["cities"]}


async def refresh_countries():
    """Reload the in-memory catalogue from MongoDB so every sync helper stays current."""
    global COUNTRIES, COUNTRY_BY_CODE, CITY_COUNTRY
    rows = await db.countries.find({"active": True}).sort("name", 1).to_list(500)
    if not rows:
        return
    COUNTRIES = [{"code": r["code"], "name": r["name"], "currency": r["currency"],
                  "tax_percent": float(r.get("tax_percent", 0)), "tax_label": r.get("tax_label", "Tax"),
                  "emergency": r.get("emergency", ""), "cities": list(r.get("cities") or [])} for r in rows]
    COUNTRY_BY_CODE = {c["code"]: c for c in COUNTRIES}
    CITY_COUNTRY = {city: c for c in COUNTRIES for city in c["cities"]}


def country_for_city(city: str) -> Optional[dict]:
    return CITY_COUNTRY.get((city or "").strip())


def country_for_currency(currency: str) -> Optional[dict]:
    return next((c for c in COUNTRIES if c["currency"] == (currency or "").upper()), None)


def tax_for(currency: str, fallback_pct: float, country_code: str = "") -> tuple[float, str]:
    """Tax follows the member's country when it shares the charging currency, else the currency's home country."""
    cur = (currency or "").upper()
    home = COUNTRY_BY_CODE.get(country_code or "")
    if home and home["currency"] == cur:
        return float(home["tax_percent"]), home["tax_label"]
    c = country_for_currency(cur)
    if c:
        return float(c["tax_percent"]), c["tax_label"]
    return float(fallback_pct), "Tax"


def fmt_money(amount: float, currency: str = "") -> str:
    cur = (currency or BASE_CURRENCY).upper()
    conf = DEFAULT_CURRENCIES.get(cur, {})
    digits = 0 if cur in ZERO_DECIMAL or cur == "INR" else 2
    return f"{conf.get('symbol', cur + ' ')}{amount:,.{digits}f}"


async def price_event(doc: dict) -> dict:
    """Organisers price in their city's own currency; we store the base amount plus an exact-currency override."""
    cur = (doc.pop("price_currency", "") or BASE_CURRENCY).upper()
    rates = await fx_rates()
    if cur not in rates:
        raise HTTPException(status_code=400, detail="We don't support that currency yet.")
    amount = round(float(doc.get("price") or 0), 2)
    rate = rates[cur] or 1.0
    doc["price_currency"] = cur
    doc["price_input"] = amount
    if cur == BASE_CURRENCY:
        doc["price"], doc["price_overrides"] = amount, {}
    else:
        doc["price"] = round(amount / rate, 2)
        doc["price_overrides"] = {cur: amount}
    return doc


def with_country(doc: dict) -> dict:
    c = country_for_city(doc.get("city", ""))
    doc["country"] = doc.get("country") or (c or {}).get("name", "")
    doc["country_code"] = (c or {}).get("code", "")
    # Descriptions and rules are authored in the rich-text editor, so they arrive as HTML.
    for field in ("description", "rules"):
        if doc.get(field):
            doc[field] = safe_html(doc[field])[:6000]
    return doc


async def currency_config() -> dict:
    s = await db.settings.find_one({}, {"currencies": 1})
    conf = (s or {}).get("currencies") or {}
    out = {k: dict(v) for k, v in DEFAULT_CURRENCIES.items()}
    for code, cfg in conf.items():
        out.setdefault(code.upper(), {"symbol": code.upper() + " ", "label": code.upper()})
        out[code.upper()].update(cfg)
    return out


async def fx_rates() -> dict:
    return {k: float(v.get("rate", 1)) for k, v in (await currency_config()).items()}


def razorpay_client():
    kid, secret = os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")
    if not kid or not secret or razorpay is None:
        return None
    return razorpay.Client(auth=(kid, secret))


EMAIL_TYPES = {"registration", "membership", "order", "event", "refund", "message", "reminder", "moderation"}
PUSH_TYPES = {"message", "reminder"}
REFERRAL_REWARD = float(os.environ.get("REFERRAL_REWARD", "3"))


# ---------------- editable email templates ----------------
# Every automated email lives here. Admins can override subject/title/body/button; {{vars}} stay dynamic.
EMAIL_TEMPLATES: dict[str, dict] = {
    "pass_reminder": {
        "label": "Pass reminder (before the event)", "group": "Payments",
        "vars": ["first_name", "item", "code", "when", "where", "qr_url", "pass_url"],
        "subject": "Coming up: {{item}} — your pass code is {{code}}",
        "title": "Your Buddilio Pass",
        "body": "<p>Hi {{first_name}},</p><p><b>{{item}}</b> is coming up — {{when}} at {{where}}.</p>"
                "<p>Show this QR at the door, or just read out your code.</p>"
                "<p style='text-align:center'><img src='{{qr_url}}' alt='Pass QR' width='160' height='160'/>"
                "<br/><b style='font-size:20px;letter-spacing:2px'>{{code}}</b></p>"
                "<p>Carry a government photo ID. The pass works once and stops working if the "
                "booking is cancelled.</p>",
        "cta_label": "Open my pass", "cta_url": "{{pass_url}}"},
    "order_refunded": {
        "label": "Order refunded", "group": "Payments",
        "vars": ["first_name", "item", "order_no", "amount", "orders_url"],
        "subject": "Refund of {{amount}} for {{item}}",
        "title": "Your refund is on its way",
        "body": "<p>Hi {{first_name}},</p><p>We've refunded <b>{{amount}}</b> for <b>{{item}}</b> "
                "(order {{order_no}}). It reaches your original payment method in 5-7 working days, "
                "depending on your bank.</p>",
        "cta_label": "View my orders", "cta_url": "{{orders_url}}"},
    "membership_expiring": {
        "label": "Membership expiring", "group": "Payments",
        "vars": ["first_name", "plan_name", "ends_on", "days", "membership_url"],
        "subject": "Your {{plan_name}} membership ends in {{days}} days",
        "title": "Keep your Buddilio benefits running",
        "body": "<p>Hi {{first_name}},</p><p>Your <b>{{plan_name}}</b> membership ends on "
                "<b>{{ends_on}}</b>. Renew now to keep unlimited messaging, member pricing and "
                "priority access to events — it takes a minute and you can pay by card without a "
                "PayPal account.</p>",
        "cta_label": "Renew my membership", "cta_url": "{{membership_url}}"},
    "vendor_document_expiring": {
        "label": "Vendor document expiring / expired", "group": "Vendors",
        "vars": ["first_name", "document", "days", "expires_on", "portal_url"],
        "subject": "Action needed: your {{document}} expires in {{days}} day(s)",
        "title": "Keep your Buddilio listings live",
        "body": "<p>Hi {{first_name}},</p><p>Your <b>{{document}}</b> on file expires on "
                "<b>{{expires_on}}</b> ({{days}} day(s) away). Mandatory documents must stay current — "
                "once one expires we pause your listings and hold settlements until a valid document is "
                "uploaded and approved.</p>",
        "cta_label": "Upload a current document", "cta_url": "{{portal_url}}"},
    "vendor_agreement_otp": {
        "label": "Vendor agreement acceptance OTP", "group": "Vendors",
        "vars": ["first_name", "otp", "agreement_number", "minutes"],
        "subject": "Your Buddilio agreement code: {{otp}}",
        "title": "Confirm your vendor agreement",
        "body": "<p>Hi {{first_name}},</p><p>Use this code to accept agreement "
                "<b>{{agreement_number}}</b>:</p><p style=\"font-size:26px;font-weight:800;letter-spacing:6px\">"
                "{{otp}}</p><p>The code expires in {{minutes}} minutes. If you didn't request it, ignore "
                "this email and tell us at info@buddilio.com.</p>",
        "cta_label": "", "cta_url": ""},
    "vendor_agreement_accepted": {
        "label": "Vendor agreement accepted", "group": "Vendors",
        "vars": ["first_name", "agreement_number", "version", "effective_date", "commercial_summary",
                 "dashboard_url", "agreement_url"],
        "subject": "Buddilio Vendor Agreement Successfully Accepted",
        "title": "Agreement {{agreement_number}} is now active",
        "body": "<p>Hi {{first_name}},</p><p>Thank you — your Buddilio Vendor Agreement is accepted and "
                "active.</p><p><b>Agreement:</b> {{agreement_number}}<br/><b>Version:</b> {{version}}<br/>"
                "<b>Effective from:</b> {{effective_date}}</p><p><b>Commercial summary</b><br/>"
                "{{commercial_summary}}</p><p>Your executed agreement is saved in your vendor portal: "
                "<a href=\"{{agreement_url}}\">download the PDF</a>.</p>",
        "cta_label": "Open my vendor dashboard", "cta_url": "{{dashboard_url}}"},
    "vendor_terms_amended": {
        "label": "Vendor commercial terms amended", "group": "Vendors",
        "vars": ["first_name", "agreement_number", "version", "changes", "effective_date", "agreement_url"],
        "subject": "Your Buddilio commercial terms have been updated",
        "title": "Please review your revised commercial terms",
        "body": "<p>Hi {{first_name}},</p><p>Your Buddilio Commercial Terms have been updated. Please review "
                "and accept the revised terms.</p><p><b>What changed</b><br/>{{changes}}</p>"
                "<p><b>Effective from:</b> {{effective_date}}</p><p>Bookings already confirmed continue on "
                "the terms recorded at the time of booking.</p>",
        "cta_label": "Review and accept", "cta_url": "{{agreement_url}}"},
    "notification": {
        "label": "In-app notification email", "group": "Members",
        "vars": ["first_name", "title", "message", "link_url"],
        "subject": "{{title}} · Buddilio", "title": "{{title}}",
        "body": "<p>Hi {{first_name}},</p><p>{{message}}</p>",
        "cta_label": "Open Buddilio", "cta_url": "{{link_url}}"},
    "welcome": {
        "label": "Welcome (email signup)", "group": "Members",
        "vars": ["first_name", "dashboard_url"],
        "subject": "Welcome to Buddilio", "title": "Welcome to Buddilio, {{first_name}}",
        "body": "<p>Your account is live. Here's how members get the most out of Buddilio:</p>"
                "<p><b>1.</b> Finish your profile so we can match you with the right companions.<br/>"
                "<b>2.</b> Browse curated experiences in your city.<br/>"
                "<b>3.</b> Message a member, then pick a night out together.</p>"
                "<p>Remember: always meet in public venues and never send money to another member.</p>",
        "cta_label": "Open my dashboard", "cta_url": "{{dashboard_url}}"},
    "welcome_google": {
        "label": "Welcome (Google signup)", "group": "Members",
        "vars": ["first_name", "welcome_url"],
        "subject": "Welcome to Buddilio", "title": "Welcome to Buddilio, {{first_name}}",
        "body": "<p>You signed in with Google, so there's no password to remember.</p>"
                "<p><b>1.</b> Confirm your city and interests.<br/>"
                "<b>2.</b> Browse curated experiences near you.<br/>"
                "<b>3.</b> Message a member, then pick a night out together.</p>"
                "<p>Remember: always meet in public venues and never send money to another member.</p>",
        "cta_label": "Finish setting up", "cta_url": "{{welcome_url}}"},
    "password_reset": {
        "label": "Password reset", "group": "Members",
        "vars": ["first_name", "reset_url"],
        "subject": "Reset your Buddilio password", "title": "Reset your Buddilio password",
        "body": "<p>Hi {{first_name}},</p><p>We received a request to reset your Buddilio password. "
                "This link expires in one hour and can only be used once.</p>"
                "<p>If you didn't ask for this, you can safely ignore this email.</p>",
        "cta_label": "Choose a new password", "cta_url": "{{reset_url}}"},
    "membership_active": {
        "label": "Membership activated", "group": "Bookings",
        "vars": ["plan_name", "receipt", "valid_until", "membership_url"],
        "subject": "Your Buddilio membership is active", "title": "{{plan_name}} is live",
        "body": "{{receipt}}<p>Valid until <b>{{valid_until}}</b>. Member pricing is applied automatically "
                "at checkout.</p>",
        "cta_label": "See member benefits", "cta_url": "{{membership_url}}"},
    "booking_confirmed": {
        "label": "Event booking confirmed", "group": "Bookings",
        "vars": ["event_title", "receipt", "when", "venue", "city", "host", "cancellation", "event_url"],
        "subject": "You're going to {{event_title}}", "title": "Booking confirmed",
        "body": "{{receipt}}<p><b>When:</b> {{when}}<br/><b>Where:</b> {{venue}}, {{city}}<br/>"
                "<b>Host:</b> {{host}}</p><p><b>Cancellation:</b> {{cancellation}}</p>"
                "<p>Your paid-ticket group chat is now open — say hi before the night.</p>",
        "cta_label": "Open event", "cta_url": "{{event_url}}"},
    "purchase_confirmed": {
        "label": "Purchase confirmed", "group": "Bookings",
        "vars": ["receipt", "orders_url"],
        "subject": "Your Buddilio purchase", "title": "Purchase confirmed",
        "body": "{{receipt}}<p>You can view this any time under My Orders.</p>",
        "cta_label": "View my orders", "cta_url": "{{orders_url}}"},
    "event_reminder": {
        "label": "Event reminder (day before)", "group": "Bookings",
        "vars": ["first_name", "event_title", "when", "venue", "city", "host", "event_url"],
        "subject": "Tomorrow: {{event_title}}", "title": "See you tomorrow",
        "body": "<p>Hi {{first_name}},</p><p><b>{{event_title}}</b> starts <b>{{when}}</b>.</p>"
                "<p><b>Venue:</b> {{venue}}, {{city}}<br/><b>Host:</b> {{host}}</p>"
                "<p>Carry a government photo ID. Meet other members in the public venue only.</p>",
        "cta_label": "View event", "cta_url": "{{event_url}}"},
    "city_live": {
        "label": "City waitlist — we're live", "group": "Growth",
        "vars": ["city", "event_count", "currency", "city_url"],
        "subject": "Buddilio is now live in {{city}}", "title": "{{city}} is open",
        "body": "<p>You asked us to tell you the moment Buddilio opened in {{city}} — it just did.</p>"
                "<p>There are <b>{{event_count}} experiences</b> on the calendar right now, priced in "
                "{{currency}}, with verified members going to each one.</p>"
                "<p>Join free, tell us what you enjoy, and book the first night that looks like you.</p>",
        "cta_label": "See what's on in {{city}}", "cta_url": "{{city_url}}"},
    "vendor_invite": {
        "label": "Organiser invitation", "group": "Organisers",
        "vars": ["inviter", "org_name", "note", "invite_days", "invite_url"],
        "subject": "You're invited to host on Buddilio", "title": "Bring your experiences to Buddilio",
        "body": "<p>{{inviter}} invited <b>{{org_name}}</b> to host on Buddilio.</p><p>{{note}}</p>"
                "<p>Set up your organiser profile, upload your documents and publish your first experience. "
                "This link expires in {{invite_days}} days.</p>",
        "cta_label": "Start my organiser signup", "cta_url": "{{invite_url}}"},
    "vendor_created": {
        "label": "Organiser account created for them", "group": "Organisers",
        "vars": ["first_name", "manager_name", "org_name", "reset_url"],
        "subject": "Your Buddilio organiser account", "title": "You're set up on Buddilio, {{first_name}}",
        "body": "<p>{{manager_name}} created an organiser account for <b>{{org_name}}</b> on Buddilio.</p>"
                "<p>Choose a password to take over the account, then publish your first experience. "
                "This link works for 7 days.</p>",
        "cta_label": "Set my password", "cta_url": "{{reset_url}}"},
    "vendor_verified": {
        "label": "Organiser verified", "group": "Organisers",
        "vars": ["org_name", "partner_url"],
        "subject": "You're verified on Buddilio", "title": "Verified",
        "body": "<p><b>{{org_name}}</b> is now a verified Buddilio organiser. Members will see the badge on "
                "your profile and on every event you host.</p>",
        "cta_label": "Open your dashboard", "cta_url": "{{partner_url}}"},
    "vendor_rejected": {
        "label": "Organiser verification rejected", "group": "Organisers",
        "vars": ["org_name", "reason", "partner_url"],
        "subject": "About your Buddilio verification", "title": "We need better documents",
        "body": "<p>Hi {{org_name}}, we couldn't verify your account yet.</p><p><b>{{reason}}</b></p>"
                "<p>Please re-upload your documents and we'll take another look.</p>",
        "cta_label": "Upload documents", "cta_url": "{{partner_url}}"},
    "console_requested": {
        "label": "Console access requested", "group": "Team",
        "vars": ["first_name", "console_url"],
        "subject": "Your Buddilio console request", "title": "Request received",
        "body": "<p>Thanks {{first_name}} — your Buddilio Vendor Console request is with our team.</p>"
                "<p>You can sign in now, but adding vendors unlocks as soon as we approve you. "
                "We usually review within one business day.</p>",
        "cta_label": "Open the console", "cta_url": "{{console_url}}"},
    "console_approved": {
        "label": "Console access approved", "group": "Team",
        "vars": ["first_name", "console_url"],
        "subject": "Your Buddilio console is ready", "title": "You're approved",
        "body": "<p>Hi {{first_name}}, your Buddilio Vendor Console is open. You can add organisers, manage "
                "their accounts and follow their events.</p>",
        "cta_label": "Open the console", "cta_url": "{{console_url}}"},
    "team_invite": {
        "label": "Team member invited", "group": "Team",
        "vars": ["inviter", "role_label", "reset_url"],
        "subject": "You've been added to the Buddilio team", "title": "Set your password",
        "body": "<p>{{inviter}} added you to the Buddilio team as <b>{{role_label}}</b>.</p>"
                "<p>Set a password to sign in. This link works for 7 days.</p>",
        "cta_label": "Set my password", "cta_url": "{{reset_url}}"},
    "account_created": {
        "label": "Account created by admin", "group": "Team",
        "vars": ["first_name", "reset_url"],
        "subject": "Your Buddilio account is ready", "title": "Set your password",
        "body": "<p>Hi {{first_name}}, the Buddilio team created an account for you. Set a password to "
                "sign in — this link works for 7 days.</p>",
        "cta_label": "Set my password", "cta_url": "{{reset_url}}"},
    "payout_reminder": {
        "label": "Weekly payout reminder (managers)", "group": "Money",
        "vars": ["first_name", "intro", "rows", "total", "currency", "console_url"],
        "subject": "Payouts due this week — {{currency}} {{total}}",
        "title": "What your vendors are owed this week",
        "body": "<p>{{intro}}</p><table width='100%' style='font-size:14px'>{{rows}}</table>"
                "<p style='margin-top:14px'><b>Total pending: {{currency}} {{total}}</b></p>",
        "cta_label": "Open the console", "cta_url": "{{console_url}}"},
    "photo_removed": {
        "label": "Photo removed / warning", "group": "Safety",
        "vars": ["first_name", "event_title", "reason", "guidelines_url"],
        "subject": "About a photo you posted on Buddilio", "title": "We removed one of your photos",
        "body": "<p>Hi {{first_name}}, a photo you added to <b>{{event_title}}</b> has been taken down.</p>"
                "<p><b>{{reason}}</b></p><p>Please keep the photo wall respectful and only post pictures "
                "where everyone in frame is happy to be seen. Repeat reports can lead to your account being "
                "suspended.</p>",
        "cta_label": "Read the guidelines", "cta_url": "{{guidelines_url}}"},
}
TPL_FIELDS = ("subject", "title", "body", "cta_label", "cta_url")


def fill(text: str, values: dict) -> str:
    return re.sub(r"{{\s*(\w+)\s*}}", lambda m: str(values.get(m.group(1), "")), text or "")


async def email_template(key: str) -> dict:
    base = EMAIL_TEMPLATES[key]
    saved = await db.email_templates.find_one({"key": key}) or {}
    return {f: (saved.get(f) if saved.get(f) not in (None, "") else base[f]) for f in TPL_FIELDS} | {
        "key": key, "label": base["label"], "group": base["group"], "vars": base["vars"],
        "customised": bool(saved)}


async def send_tpl(key: str, to: str, values: dict) -> bool:
    """Send one of the registered emails, honouring any admin edits to its wording."""
    tpl = await email_template(key)
    return await send_email(to, fill(tpl["subject"], values),
                            wrap(fill(tpl["title"], values), fill(tpl["body"], values),
                                 fill(tpl["cta_label"], values), fill(tpl["cta_url"], values)))


def first_name(name: str) -> str:
    return (name or "there").split(" ")[0]


async def notify(user_id: str, title: str, body: str, ntype: str = "system", link: str = "",
                 email: bool = True, cta: str = ""):
    await db.notifications.insert_one({
        "user_id": user_id, "title": title, "body": body, "type": ntype, "link": link,
        "read": False, "created_at": iso(now_utc()),
    })
    want_email = email and ntype in EMAIL_TYPES
    want_push = ntype in PUSH_TYPES and push_enabled()
    if not (want_email or want_push):
        return
    try:
        user = await db.users.find_one({"_id": ObjectId(user_id)},
                                       {"email": 1, "notification_prefs": 1, "full_name": 1})
    except Exception:
        return
    if not user:
        return
    prefs = user.get("notification_prefs") or {}
    if want_push and prefs.get("push", True):
        await push_to(db, user_id, {"title": title, "body": body,
                                    "url": link or "/dashboard", "tag": ntype})
    if want_email and prefs.get("email", True):
        await send_tpl("notification", user["email"], {
            "first_name": first_name(user.get("full_name")), "title": title, "message": body,
            "link_url": f"{FRONTEND_URL}{link}" if link else ""})


async def membership_active(user_id: str) -> Optional[dict]:
    m = await db.user_memberships.find_one(
        {"user_id": user_id, "status": "active", "ends_at": {"$gt": iso(now_utc())}},
        sort=[("ends_at", -1)])
    return clean(m) if m else None


FREE_PLAN_LIMITS = {"plan_name": "Free", "messages_per_week": 5, "hangouts_access": False,
                    "premium_filters": False, "priority_access": False, "concierge_support": False,
                    "discount_percent": 0.0}


async def plan_limits(user_id: str) -> dict:
    """What this member is allowed to do — from their plan if they have one, else the free defaults."""
    member = await membership_active(user_id)
    s = await db.settings.find_one({}, {"free_messages_per_week": 1}) or {}
    free = {**FREE_PLAN_LIMITS, "messages_per_week": int(s.get("free_messages_per_week", 5))}
    if not member:
        return free
    plan = None
    if member.get("plan_id"):
        try:
            plan = await db.membership_plans.find_one({"_id": ObjectId(member["plan_id"])})
        except Exception:
            plan = None
    if not plan:
        return {**free, "plan_name": member.get("plan_name", "Member")}
    return {"plan_name": plan.get("name", member.get("plan_name", "Member")),
            "messages_per_week": int(plan.get("messages_per_week") or 0),
            "hangouts_access": bool(plan.get("hangouts_access")),
            "premium_filters": bool(plan.get("premium_filters")),
            "priority_access": bool(plan.get("priority_access")),
            "concierge_support": bool(plan.get("concierge_support")),
            "discount_percent": float(plan.get("discount_percent") or 0)}


def week_start() -> str:
    d = now_utc()
    return iso((d - timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0))


async def messages_left(user_id: str, limits: Optional[dict] = None) -> Optional[int]:
    """None means unlimited."""
    lim = limits or await plan_limits(user_id)
    cap = int(lim.get("messages_per_week") or 0)
    if cap <= 0:
        return None
    used = await db.messages.count_documents({"sender_id": user_id, "created_at": {"$gte": week_start()}})
    return max(cap - used, 0)


async def load_many(collection, ids, fields: Optional[dict] = None) -> dict:
    """Fetch a set of documents by id in one round-trip, keyed by their string id."""
    oids = []
    for i in set(ids):
        try:
            oids.append(ObjectId(i))
        except Exception:
            continue
    if not oids:
        return {}
    cur = collection.find({"_id": {"$in": oids}}, fields) if fields else collection.find({"_id": {"$in": oids}})
    return {str(d["_id"]): d for d in await cur.limit(len(oids)).to_list(len(oids))}


# ---------------- referrals & credit ----------------
def gen_ref_code(name: str) -> str:
    base = "".join(ch for ch in (name or "").upper() if ch.isalpha())[:6] or "BUDDY"
    return f"{base}{secrets.token_hex(2).upper()}"


async def ensure_ref_code(user_doc: dict) -> str:
    if user_doc.get("referral_code"):
        return user_doc["referral_code"]
    code = ""
    for _ in range(5):
        candidate = gen_ref_code(user_doc.get("full_name", ""))
        if not await db.users.find_one({"referral_code": candidate}):
            code = candidate
            break
    code = code or "BUD" + secrets.token_hex(4).upper()
    await db.users.update_one({"_id": user_doc["_id"]}, {"$set": {"referral_code": code}})
    return code


async def credit_balance(user_id: str) -> float:
    docs = await db.credits.find({"user_id": user_id}, {"amount": 1}).limit(500).to_list(500)
    return round(sum(d["amount"] for d in docs), 2)


BADGES = [(10, "Legend"), (5, "Ambassador"), (3, "Connector"), (1, "Starter")]


def badge_for(count: int) -> dict:
    """Lifetime rewarded invites decide the badge; `next` is the invites needed for the following tier."""
    nxt = next((n for n, _ in reversed(BADGES) if n > count), 0)
    for need, name in BADGES:
        if count >= need:
            return {"name": name, "at": need, "next": nxt}
    return {"name": "", "at": 0, "next": 1}


async def record_signup_consents(user_id: str, email: str, request: Optional[Request] = None):
    """A sign-up ticks the current Terms, Privacy and Guidelines, so store them as accepted versions."""
    for slug in ("terms", "privacy", "guidelines"):
        req = await db.policy_acceptance_required.find_one({"slug": slug})
        page = await db.cms_pages.find_one({"slug": slug}, {"policy_version": 1})
        version = int((req or {}).get("version") or (page or {}).get("policy_version") or 1)
        await db.policy_acceptances.insert_one({
            "user_id": user_id, "email": email, "slug": slug, "version": version,
            "accepted_at": iso(now_utc()), "source": "registration",
            "ip_address": (request.client.host if request and request.client else ""),
            "user_agent": (request.headers.get("user-agent", "")[:300] if request else "")})


async def register_referral(code: str, invitee_id: str, invitee_name: str):
    code = (code or "").strip().upper()
    if not code:
        return
    ref = await db.users.find_one({"referral_code": code}, {"full_name": 1})
    if not ref or str(ref["_id"]) == invitee_id:
        return
    if await db.referrals.find_one({"invitee_id": invitee_id}):
        return
    await db.referrals.insert_one({
        "referrer_id": str(ref["_id"]), "invitee_id": invitee_id, "invitee_name": invitee_name,
        "code": code, "status": "joined", "created_at": iso(now_utc())})
    await notify(str(ref["_id"]), "Your invite was accepted",
                 f"{invitee_name.split(' ')[0]} joined Buddilio with your link. "
                 f"You earn {fmt_money(REFERRAL_REWARD)} credit on their first paid booking.",
                 "system", "/referrals", email=False)


async def award_referral(invitee_id: str, order: dict):
    ref = await db.referrals.find_one({"invitee_id": invitee_id, "status": "joined"})
    if not ref:
        return
    await db.referrals.update_one({"_id": ref["_id"]},
                                 {"$set": {"status": "rewarded", "rewarded_at": iso(now_utc()),
                                           "order_id": str(order["_id"])}})
    await db.credits.insert_one({
        "user_id": ref["referrer_id"], "amount": REFERRAL_REWARD, "type": "earned",
        "reason": f"Referral bonus — {ref.get('invitee_name', 'a friend')} made their first booking",
        "referral_id": str(ref["_id"]), "created_at": iso(now_utc())})
    await notify(ref["referrer_id"], f"You earned {fmt_money(REFERRAL_REWARD)} Buddilio credit",
                 f"{ref.get('invitee_name', 'Your friend')} completed their first booking. "
                 "Your credit is applied automatically at your next checkout.",
                 "order", "/referrals")


# ---------------- models ----------------
class RegisterIn(BaseModel):
    full_name: str
    email: EmailStr
    mobile: str
    password: str = Field(min_length=10)
    dob: str
    gender: str
    city: str
    bio: str = ""
    captcha_id: str = ""
    captcha_answer: str = ""
    website: str = ""          # honeypot — real people never fill this
    photo: str = ""
    interests: List[str] = []
    event_categories: List[str] = []
    lifestyle: List[str] = []
    is_adult: bool = False
    accept_terms: bool = False
    accept_privacy: bool = False
    accept_guidelines: bool = False
    role: str = "user"
    org_name: str = ""
    country: str = ""
    referral_code: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    captcha_id: str = ""
    captcha_answer: str = ""
    website: str = ""


class GoogleSessionIn(BaseModel):
    session_id: str
    referral_code: str = ""


class OnboardingIn(BaseModel):
    dob: str
    city: str
    gender: str = "prefer not to say"
    mobile: str = ""
    country: str = ""
    bio: str = ""
    photo: str = ""
    interests: List[str] = []
    event_categories: List[str] = []
    lifestyle: List[str] = []
    is_adult: bool = False
    accept_terms: bool = False


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    full_name: Optional[str] = None
    bio: Optional[str] = None
    city: Optional[str] = None
    photo: Optional[str] = None
    interests: Optional[List[str]] = None
    event_categories: Optional[List[str]] = None
    lifestyle: Optional[List[str]] = None
    country: Optional[str] = None
    privacy: Optional[dict] = None
    notification_prefs: Optional[dict] = None


class EventIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    description: str = ""
    category: str
    city: str
    country: str = ""
    venue: str = ""
    starts_at: str
    ends_at: str = ""
    cover_image: str = ""
    gallery: List[str] = []
    price: float = 0
    price_currency: str = ""
    capacity: int = 50
    rules: str = ""
    cancellation_policy: str = ""
    approval_mode: str = "instant"  # instant | organizer | admin
    featured: bool = False


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    price: float
    duration_days: int = 365
    description: str = ""
    benefits: List[str] = []
    discount_percent: float = 0
    price_overrides: dict = {}
    # What the plan actually unlocks — edited in Admin → Memberships and enforced at runtime.
    messages_per_week: int = 0          # 0 = unlimited
    hangouts_access: bool = False
    premium_filters: bool = False
    priority_access: bool = False
    concierge_support: bool = False
    active: bool = True


class ProductIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    description: str = ""
    price: float
    discount_percent: float = 0
    tax_percent: float = 18
    image: str = ""
    validity_days: int = 30
    city: str = "Global"
    inventory: int = 100
    member_discount_percent: float = 10
    price_overrides: dict = {}
    active: bool = True


class CouponIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str
    discount_type: str = "percent"  # percent | fixed
    value: float = 10
    min_order: float = 0
    usage_limit: int = 100
    members_only: bool = False
    expires_at: str = ""
    active: bool = True


class CheckoutIn(BaseModel):
    kind: str  # membership | product | event | companion | wallet | travel | provider_fee
    item_id: str
    quantity: int = 1
    coupon_code: str = ""
    currency: str = ""              # ignored: Buddilio always charges in the base currency
    use_credit: bool = True


class PushSubIn(BaseModel):
    endpoint: str
    keys: dict
    expirationTime: Optional[int] = None


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class VerifyPaymentIn(BaseModel):
    order_id: str
    gateway_payment_id: str = ""
    simulate: str = "success"  # success | failure


class MessageIn(BaseModel):
    body: str = ""
    attachment_path: str = ""


class ReportIn(BaseModel):
    target_type: str  # user | event | conversation
    target_id: str
    reason: str
    details: str = ""


app = FastAPI(title="Buddilio API")
api = APIRouter(prefix="/api")


# ---------------- auth routes ----------------
def set_cookies(response: Response, token: str):
    response.set_cookie("access_token", token, httponly=True, secure=True,
                        samesite="none", max_age=604800, path="/")


def age_from_dob(dob: str) -> int:
    try:
        d = datetime.fromisoformat(dob[:10])
        t = now_utc()
        return t.year - d.year - ((t.month, t.day) < (d.month, d.day))
    except Exception:
        return 0


@api.get("/captcha")
async def get_captcha():
    """Issues a short human challenge; the answer never leaves the server."""
    doc = botguard.new_challenge()
    await db.captchas.insert_one({**doc, "used": False, "created_at": iso(now_utc())})
    return {"captcha_id": doc["id"], "question": doc["question"]}


async def guard(request: Request, action: str, captcha_id: str, answer: str, honeypot: str = ""):
    """Rate limit + honeypot + challenge. Raises the right 4xx for humans."""
    if honeypot.strip():
        raise HTTPException(status_code=400, detail="That request looked automated. Please try again.")
    ip = botguard.client_ip(request)
    limit, minutes = botguard.LIMITS.get(action, (10, 60))
    since = iso(now_utc() - timedelta(minutes=minutes))
    hits = await db.bot_hits.count_documents({"ip": ip, "action": action, "at": {"$gte": since}})
    await db.bot_hits.insert_one({"ip": ip, "action": action, "at": iso(now_utc())})
    if hits >= limit:
        raise HTTPException(status_code=429,
                            detail=f"Too many attempts from this device. Please try again in {minutes} minutes.")
    doc = await db.captchas.find_one({"id": captcha_id, "used": False})
    if not doc or doc["expires_at"] < iso(now_utc()):
        raise HTTPException(status_code=400,
                            detail="Please answer the quick human check shown below and try again.")
    if not botguard.check_answer(doc, answer):
        raise HTTPException(status_code=400, detail="That verification answer wasn't right. Please try again.")
    await db.captchas.update_one({"_id": doc["_id"]}, {"$set": {"used": True, "used_at": iso(now_utc())}})


@api.post("/auth/register")
async def register(payload: RegisterIn, response: Response, request: Request):
    await guard(request, "register", payload.captcha_id, payload.captcha_answer, payload.website)
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    age = age_from_dob(payload.dob)
    if age < 21:
        raise HTTPException(status_code=400, detail="You must be at least 21 years old to join Buddilio.")
    if not all([payload.is_adult, payload.accept_terms, payload.accept_privacy,
                payload.accept_guidelines]):
        raise HTTPException(status_code=400,
                            detail="Please confirm you are 21+ and accept the Terms, Privacy Policy and "
                                   "Community Guidelines.")
    if len(payload.mobile.strip()) < 8:
        raise HTTPException(status_code=400, detail="Please enter a valid mobile number.")
    role = "partner" if payload.role == "partner" else "user"
    doc = {
        "full_name": payload.full_name, "email": email, "mobile": payload.mobile,
        "password_hash": hash_password(payload.password), "role": role, "status": "active",
        "dob": payload.dob, "age": age, "gender": payload.gender, "city": payload.city,
        "bio": safe_html(payload.bio or "")[:4000], "photo": payload.photo, "interests": payload.interests,
        "event_categories": payload.event_categories, "lifestyle": payload.lifestyle,
        "verified": False, "email_verified": False, "org_name": payload.org_name,
        "country": payload.country or (country_for_city(payload.city) or {}).get("name", ""),
        "country_code": (country_for_city(payload.city) or {}).get("code", ""),
        "privacy": {"profile_visibility": "public", "who_can_message": "everyone"},
        "notification_prefs": {"email": True, "in_app": True, "sms": False, "push": True},
        "blocked": [], "connections": [], "saved_events": [],
        "created_at": iso(now_utc()),
    }
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    await record_signup_consents(uid, email, request)
    await register_referral(payload.referral_code, uid, payload.full_name)
    await notify(uid, "Welcome to Buddilio", "Complete your profile to get better companion matches.", "registration", "/profile")
    asyncio.create_task(send_tpl("welcome", email, {"first_name": first_name(payload.full_name),
                                                   "dashboard_url": f"{FRONTEND_URL}/dashboard"}))
    token = create_access_token(uid, email, role)
    set_cookies(response, token)
    user = clean(await db.users.find_one({"_id": res.inserted_id}))
    return {"access_token": token, "user": user}


@api.post("/auth/login")
async def login(payload: LoginIn, request: Request, response: Response):
    email = payload.email.lower().strip()
    ident = f"email:{email}"
    att = await db.login_attempts.find_one({"identifier": ident})
    if att and att.get("count", 0) >= 2:
        # Only ask a human question once someone is clearly guessing.
        await guard(request, "login", payload.captcha_id, payload.captcha_answer, payload.website)
    elif payload.website.strip():
        raise HTTPException(status_code=400, detail="That request looked automated. Please try again.")
    if att and att.get("count", 0) >= 5 and att.get("locked_until", "") > iso(now_utc()):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        await db.login_attempts.update_one(
            {"identifier": ident},
            {"$inc": {"count": 1}, "$set": {"locked_until": iso(now_utc() + timedelta(minutes=15))}},
            upsert=True)
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if user.get("status") == "banned":
        raise HTTPException(status_code=403, detail="This account has been banned.")
    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="This account is suspended. Contact support.")
    await db.login_attempts.delete_one({"identifier": ident})
    token = create_access_token(str(user["_id"]), email, user.get("role", "user"),
                                user.get("token_version", 0))
    set_cookies(response, token)
    return {"access_token": token, "user": clean(user)}


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    user["membership"] = await membership_active(user["id"])
    user["permissions"] = sorted(perms_of(user))
    return user


@api.post("/auth/forgot-password")
async def forgot_password(body: dict):
    email = (body.get("email") or "").lower().strip()
    user = await db.users.find_one({"email": email})
    if user:
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": str(user["_id"]), "used": False,
            "expires_at": now_utc() + timedelta(hours=1)})
        logger.info(f"[Buddilio] Password reset link: /reset-password?token={token}")
        # Don't make the user wait on the mail provider.
        asyncio.create_task(send_tpl("password_reset", user["email"], {
            "first_name": first_name(user.get("full_name")),
            "reset_url": f"{FRONTEND_URL}/reset-password?token={token}"}))
    return {"message": "If that email exists, a reset link has been sent."}


@api.post("/auth/reset-password")
async def reset_password(body: dict):
    token, new_password = body.get("token"), body.get("password") or ""
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    rec = await db.password_reset_tokens.find_one({"token": token, "used": False})
    if not rec:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    await db.users.update_one({"_id": ObjectId(rec["user_id"])},
                              {"$set": {"password_hash": hash_password(new_password)}})
    await db.password_reset_tokens.update_one({"_id": rec["_id"]}, {"$set": {"used": True}})
    return {"message": "Password updated. You can now log in."}


GOOGLE_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


@api.post("/auth/google/session")
async def google_session(payload: GoogleSessionIn, response: Response):
    """Exchanges the one-time Emergent OAuth session_id for a Buddilio session."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(GOOGLE_SESSION_URL, headers={"X-Session-ID": payload.session_id})
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach Google sign-in. Please try again.")
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="That Google sign-in link has expired. Please try again.")
    data = r.json()
    email = (data.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=401, detail="Google did not share an email address for this account.")
    name = data.get("name") or email.split("@")[0]
    user = await db.users.find_one({"email": email})
    is_new = user is None

    if user:
        if user.get("status") == "banned":
            raise HTTPException(status_code=403, detail="This account has been banned.")
        if user.get("status") == "suspended":
            raise HTTPException(status_code=403, detail="This account is suspended. Contact support.")
        upd = {"google_id": data.get("id", ""), "google_linked": True, "email_verified": True}
        if not user.get("photo") and data.get("picture"):
            upd["photo"] = data["picture"]
        await db.users.update_one({"_id": user["_id"]}, {"$set": upd})
        user = await db.users.find_one({"_id": user["_id"]})
    else:
        doc = {
            "full_name": name, "email": email, "mobile": "",
            "password_hash": hash_password(secrets.token_urlsafe(24)), "role": "user", "status": "active",
            "dob": "", "age": 0, "gender": "", "city": "", "country": "", "country_code": "", "bio": "",
            "photo": data.get("picture") or "", "interests": [], "event_categories": [], "lifestyle": [],
            "verified": False, "email_verified": True, "auth_provider": "google",
            "google_id": data.get("id", ""), "google_linked": True, "profile_complete": False,
            "privacy": {"profile_visibility": "public", "who_can_message": "everyone"},
            "notification_prefs": {"email": True, "in_app": True, "sms": False, "push": True},
            "blocked": [], "connections": [], "saved_events": [], "created_at": iso(now_utc()),
        }
        res = await db.users.insert_one(doc)
        user = await db.users.find_one({"_id": res.inserted_id})
        uid = str(res.inserted_id)
        await ensure_ref_code(user)
        await record_signup_consents(uid, email, None)
        await register_referral(payload.referral_code, uid, name)
        await notify(uid, "Welcome to Buddilio",
                     "Finish the last step so we can match you with the right companions.",
                     "registration", "/welcome")
        asyncio.create_task(send_tpl("welcome_google", email, {"first_name": first_name(name),
                                                              "welcome_url": f"{FRONTEND_URL}/welcome"}))
        user = await db.users.find_one({"_id": res.inserted_id})

    token = create_access_token(str(user["_id"]), email, user.get("role", "user"))
    set_cookies(response, token)
    return {"access_token": token, "user": clean(user), "is_new": is_new}


@api.post("/auth/onboarding")
async def complete_onboarding(payload: OnboardingIn, user: dict = Depends(get_current_user)):
    """One-time profile completion for members who joined through Google (21+ gate lives here)."""
    age = age_from_dob(payload.dob)
    if age < 21:
        raise HTTPException(status_code=400, detail="You must be at least 21 years old to join Buddilio.")
    if not payload.is_adult or not payload.accept_terms:
        raise HTTPException(status_code=400, detail="Please confirm your age and accept the policies.")
    city = payload.city.strip()
    if not city:
        raise HTTPException(status_code=400, detail="Please choose your city.")
    c = country_for_city(city) or {}
    upd = {
        "dob": payload.dob, "age": age, "gender": payload.gender, "city": city,
        "country": payload.country or c.get("name", ""), "country_code": c.get("code", ""),
        "bio": safe_html(payload.bio or "")[:4000], "interests": payload.interests,
        "event_categories": payload.event_categories, "lifestyle": payload.lifestyle,
        "profile_complete": True,
    }
    if payload.mobile.strip():
        upd["mobile"] = payload.mobile.strip()
    if payload.photo:
        upd["photo"] = payload.photo
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": upd})
    return clean(await db.users.find_one({"_id": ObjectId(user["id"])}))


# ---------------- profiles / discover ----------------
@api.put("/users/me")
async def update_me(payload: ProfileIn, user: dict = Depends(get_current_user)):
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if isinstance(upd.get("bio"), str):
        upd["bio"] = safe_html(upd["bio"])[:4000]
    if upd.get("city"):
        c = country_for_city(upd["city"])
        if c:
            upd["country"], upd["country_code"] = c["name"], c["code"]
    if upd:
        await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": upd})
    return clean(await db.users.find_one({"_id": ObjectId(user["id"])}))


PUBLIC_FIELDS = {"full_name": 1, "age": 1, "city": 1, "bio": 1, "photo": 1, "interests": 1,
                 "event_categories": 1, "lifestyle": 1, "created_at": 1, "verified": 1, "role": 1}


@api.get("/discover")
async def discover(city: str = "", country: str = "", interest: str = "", category: str = "",
                   min_age: int = 21, max_age: int = 99, q: str = "",
                   page: int = 1, limit: int = 12, user: dict = Depends(get_current_user)):
    me_doc = await db.users.find_one({"_id": ObjectId(user["id"])})
    blocked = me_doc.get("blocked", [])
    flt: dict[str, Any] = {"role": "user", "status": "active",
                           "_id": {"$nin": [ObjectId(b) for b in blocked] + [ObjectId(user["id"])]},
                           "privacy.profile_visibility": {"$ne": "private"}}
    if city:
        flt["city"] = city
    if country:
        flt["country"] = country
    if interest:
        flt["interests"] = interest
    if category:
        flt["event_categories"] = category
    if q:
        flt["full_name"] = {"$regex": q, "$options": "i"}
    flt["age"] = {"$gte": min_age, "$lte": max_age}
    total = await db.users.count_documents(flt)
    cur = db.users.find(flt, PUBLIC_FIELDS).skip((page - 1) * limit).limit(limit)
    items = [clean(d) for d in await cur.to_list(limit)]
    ids = [c["id"] for c in items]
    active = {m["user_id"] for m in await db.user_memberships.find(
        {"user_id": {"$in": ids}, "status": "active", "ends_at": {"$gt": iso(now_utc())}},
        {"user_id": 1}).limit(len(ids) or 1).to_list(len(ids) or 1)} if ids else set()
    for c in items:
        c["membership"] = c["id"] in active
    return {"items": items, "total": total, "page": page}


@api.get("/users/{user_id}")
async def get_user(user_id: str, user: dict = Depends(get_current_user)):
    try:
        doc = await db.users.find_one({"_id": ObjectId(user_id)}, PUBLIC_FIELDS)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user id")
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    out = clean(doc)
    out["events_attended"] = await db.event_participants.count_documents(
        {"user_id": user_id, "status": "confirmed"})
    out["membership"] = bool(await membership_active(user_id))
    out["is_connected"] = user_id in (await db.users.find_one({"_id": ObjectId(user["id"])})).get("connections", [])
    return out


@api.post("/users/{user_id}/connect")
async def connect(user_id: str, user: dict = Depends(get_current_user)):
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$addToSet": {"connections": user_id}})
    await notify(user_id, "New connection", f"{user['full_name']} connected with you on Buddilio.",
                 "connection", "/discover")
    return {"ok": True}


@api.post("/users/{user_id}/block")
async def block(user_id: str, user: dict = Depends(get_current_user)):
    await db.users.update_one({"_id": ObjectId(user["id"])},
                              {"$addToSet": {"blocked": user_id}, "$pull": {"connections": user_id}})
    return {"ok": True}


@api.post("/reports")
async def create_report(payload: ReportIn, user: dict = Depends(get_current_user)):
    await db.reports.insert_one({
        "reporter_id": user["id"], "reporter_email": user["email"],
        "target_type": payload.target_type, "target_id": payload.target_id,
        "reason": payload.reason, "details": payload.details, "status": "open",
        "created_at": iso(now_utc())})
    return {"message": "Report submitted. Our safety team will review it."}


# ---------------- events ----------------
@api.get("/events")
async def list_events(q: str = "", city: str = "", country: str = "", category: str = "", max_price: float = -1,
                      featured: Optional[bool] = None, when: str = "", sort: str = "date",
                      verified_only: bool = False, page: int = 1, limit: int = 12):
    flt: dict[str, Any] = {"status": "published"}
    if verified_only:
        hosts = await db.users.find({"role": "partner", "verified": True}, {"_id": 1}).limit(2000).to_list(2000)
        flt["partner_id"] = {"$in": [str(h["_id"]) for h in hosts] or ["none"]}
    if q:
        flt["title"] = {"$regex": q, "$options": "i"}
    if city:
        flt["city"] = city
    if country:
        flt["country"] = country
    if category:
        flt["category"] = category
    if max_price >= 0:
        flt["price"] = {"$lte": max_price}
    if featured:
        flt["featured"] = True
    if when == "upcoming":
        flt["starts_at"] = {"$gte": iso(now_utc())}
    if when == "past":
        flt["status"] = "completed"
    elif sort == "rating":
        flt["status"] = {"$in": ["published", "completed"]}
    total = await db.events.count_documents(flt)
    sort_key = [("rating", -1)] if sort == "rating" else [("participant_count", -1)] if sort == "popular" else [("starts_at", 1)]
    docs = await db.events.find(flt).sort(sort_key).skip((page - 1) * limit).limit(limit).to_list(limit)
    items = [clean(d) for d in docs]
    verified_hosts = await load_many(db.users, [e.get("partner_id", "") for e in items], {"verified": 1})
    for e in items:
        e["partner_verified"] = bool((verified_hosts.get(e.get("partner_id", "")) or {}).get("verified"))
    rated = [e["id"] for e in items if e.get("rating_count")]
    if rated:
        # One pass for the highlighted review of every rated event, then one for their authors.
        tops: dict[str, dict] = {}
        for r in await db.reviews.find(
                {"event_id": {"$in": rated}, "status": {"$ne": "hidden"},
                 "comment": {"$nin": ["", None]}},
                sort=[("rating", -1), ("created_at", -1)]).limit(1000).to_list(1000):
            tops.setdefault(r["event_id"], r)
        author_ids = []
        for r in tops.values():
            try:
                author_ids.append(ObjectId(r["user_id"]))
            except Exception:
                continue
        names = {str(u["_id"]): u.get("full_name", "Member") for u in await db.users.find(
            {"_id": {"$in": author_ids}}, {"full_name": 1}).limit(len(author_ids) or 1).to_list(len(author_ids) or 1)}
        for e in items:
            top = tops.get(e["id"])
            if top:
                e["top_review"] = {"rating": top["rating"], "comment": top["comment"][:160],
                                   "user_name": names.get(top["user_id"], "Member").split(" ")[0]}
    return {"items": items, "total": total, "page": page}


@api.get("/events/{event_id}")
async def get_event(event_id: str, user: Optional[dict] = Depends(optional_user)):
    try:
        doc = await db.events.find_one({"_id": ObjectId(event_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event id")
    if not doc:
        raise HTTPException(status_code=404, detail="Event not found")
    ev = clean(doc)
    if ev["status"] not in ("published", "completed") and not (user and (user["role"] == "admin" or ev.get("partner_id") == user["id"])):
        raise HTTPException(status_code=403, detail="This event is not published yet.")
    parts = await db.event_participants.find({"event_id": event_id, "status": "confirmed"}).limit(200).to_list(200)
    revs = await db.reviews.find({"event_id": event_id, "status": {"$ne": "hidden"}}, {"rating": 1}).limit(500).to_list(500)
    ev["rating"] = round(sum(r["rating"] for r in revs) / len(revs), 2) if revs else 0
    ev["rating_count"] = len(revs)
    ev["participants"] = []
    ids = []
    for p in parts[:20]:
        try:
            ids.append(ObjectId(p["user_id"]))
        except Exception:
            continue
    if ids:
        ev["participants"] = [clean(u) for u in await db.users.find(
            {"_id": {"$in": ids}}, {"full_name": 1, "photo": 1, "city": 1}).limit(20).to_list(20)]
    ev["participant_count"] = len(parts)
    ev["seats_left"] = max(ev.get("capacity", 0) - len(parts), 0)
    ev["partner_verified"] = False
    if ev.get("partner_id"):
        host = await db.users.find_one({"_id": ObjectId(ev["partner_id"])}, {"verified": 1})
        ev["partner_verified"] = bool(host and host.get("verified"))
    if user:
        mine = await db.event_participants.find_one({"event_id": event_id, "user_id": user["id"]})
        ev["my_status"] = mine["status"] if mine else None
    return ev


@api.post("/events/{event_id}/join")
async def join_event(event_id: str, user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"_id": ObjectId(event_id), "status": "published"})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    if (ev.get("ends_at") or ev["starts_at"]) < iso(now_utc()):
        raise HTTPException(status_code=400, detail="This experience has already finished.")
    if await db.event_participants.find_one({"event_id": event_id, "user_id": user["id"]}):
        raise HTTPException(status_code=400, detail="You have already joined or requested this event.")
    count = await db.event_participants.count_documents({"event_id": event_id, "status": "confirmed"})
    if count >= ev.get("capacity", 0):
        raise HTTPException(status_code=400, detail="This event is fully booked.")
    if ev.get("price", 0) > 0:
        raise HTTPException(status_code=400, detail="This is a paid event. Please buy a pass to join.")
    status = "confirmed" if ev.get("approval_mode", "instant") == "instant" else "pending"
    await db.event_participants.insert_one({
        "event_id": event_id, "user_id": user["id"], "status": status,
        "created_at": iso(now_utc())})
    if status == "confirmed":
        await db.events.update_one({"_id": ev["_id"]}, {"$inc": {"participant_count": 1}})
    await notify(user["id"], "Event booking " + status,
                 f"Your spot for {ev['title']} is {status}.", "event", f"/events/{event_id}")
    return {"status": status}


@api.post("/events/{event_id}/cancel")
async def cancel_participation(event_id: str, user: dict = Depends(get_current_user)):
    res = await db.event_participants.delete_one({"event_id": event_id, "user_id": user["id"]})
    if res.deleted_count:
        await db.events.update_one({"_id": ObjectId(event_id)}, {"$inc": {"participant_count": -1}})
    return {"ok": True}


@api.post("/events/{event_id}/save")
async def save_event(event_id: str, user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"_id": ObjectId(user["id"])})
    if event_id in u.get("saved_events", []):
        await db.users.update_one({"_id": u["_id"]}, {"$pull": {"saved_events": event_id}})
        return {"saved": False}
    await db.users.update_one({"_id": u["_id"]}, {"$addToSet": {"saved_events": event_id}})
    return {"saved": True}


@api.get("/me/events")
async def my_events(user: dict = Depends(get_current_user)):
    parts = await db.event_participants.find({"user_id": user["id"]}).limit(200).to_list(200)
    events = await load_many(db.events, [p["event_id"] for p in parts])
    out = []
    for p in parts:
        ev = events.get(p["event_id"])
        if ev:
            e = clean(ev)
            e["my_status"] = p["status"]
            out.append(e)
    return {"items": out}


@api.get("/me/saved-events")
async def saved_events(user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"_id": ObjectId(user["id"])})
    ids = [ObjectId(i) for i in u.get("saved_events", [])]
    docs = await db.events.find({"_id": {"$in": ids}}).limit(100).to_list(100)
    return {"items": [clean(d) for d in docs]}


# ---------------- partner ----------------
@api.post("/partner/events")
async def create_event(payload: EventIn, submit: bool = False, user: dict = Depends(partner_only)):
    doc = await price_event(with_country(payload.model_dump()))
    doc.update({"partner_id": user["id"], "partner_name": user.get("org_name") or user["full_name"],
                "status": "submitted" if submit else "draft", "participant_count": 0,
                "created_at": iso(now_utc())})
    res = await db.events.insert_one(doc)
    await audit(user, "event.create", "event", str(res.inserted_id), {"title": payload.title})
    return clean(await db.events.find_one({"_id": res.inserted_id}))


@api.put("/partner/events/{event_id}")
async def update_event(event_id: str, payload: EventIn, user: dict = Depends(partner_only)):
    ev = await db.events.find_one({"_id": ObjectId(event_id)})
    if not ev or (user["role"] != "admin" and ev.get("partner_id") != user["id"]):
        raise HTTPException(status_code=404, detail="Event not found")
    await db.events.update_one({"_id": ev["_id"]},
                               {"$set": await price_event(with_country(payload.model_dump()))})
    return clean(await db.events.find_one({"_id": ev["_id"]}))


@api.post("/partner/events/{event_id}/submit")
async def submit_event(event_id: str, user: dict = Depends(partner_only)):
    ev = await db.events.find_one({"_id": ObjectId(event_id)})
    if not ev or (user["role"] != "admin" and ev.get("partner_id") != user["id"]):
        raise HTTPException(status_code=404, detail="Event not found")
    await db.events.update_one({"_id": ev["_id"]}, {"$set": {"status": "submitted"}})
    admin = await db.users.find_one({"role": "admin"})
    if admin:
        await notify(str(admin["_id"]), "Event awaiting review",
                     f"{ev['title']} was submitted for approval.", "moderation", "/admin/events")
    return {"status": "submitted"}


@api.get("/partner/events")
async def partner_events(user: dict = Depends(partner_only)):
    docs = await db.events.find({"partner_id": user["id"]}).sort([("created_at", -1)]).limit(200).to_list(200)
    return {"items": [clean(d) for d in docs]}


@api.get("/partner/stats")
async def partner_stats(user: dict = Depends(partner_only)):
    evs = await db.events.find({"partner_id": user["id"]}).limit(500).to_list(500)
    ids = [str(e["_id"]) for e in evs]
    parts = await db.event_participants.count_documents({"event_id": {"$in": ids}})
    orders = await db.orders.find({"ref_id": {"$in": ids}, "payment_status": "paid"}).limit(1000).to_list(1000)
    revenue = sum(o.get("total", 0) for o in orders)
    payouts = await db.payouts.find({"partner_id": user["id"]}).limit(500).to_list(500)
    revs = await db.reviews.find({"partner_id": user["id"], "status": {"$ne": "hidden"}}, {"rating": 1}).limit(2000).to_list(2000)
    return {"events": len(evs), "published": sum(1 for e in evs if e.get("status") == "published"),
            "pending": sum(1 for e in evs if e.get("status") == "submitted"),
            "completed": sum(1 for e in evs if e.get("status") == "completed"),
            "participants": parts, "revenue": revenue,
            "payout_due": round(sum(p["net"] for p in payouts if p["status"] == "pending"), 2),
            "payout_paid": round(sum(p["net"] for p in payouts if p["status"] == "paid"), 2),
            "rating": round(sum(r["rating"] for r in revs) / len(revs), 2) if revs else 0,
            "rating_count": len(revs)}


@api.get("/partner/door-takings")
async def partner_door_takings(user: dict = Depends(get_current_user)):
    """What this organiser collected at the door, and what commission Buddilio is owed on it."""
    evs = await db.events.find({"partner_id": user["id"]}, {"title": 1}).limit(500).to_list(500)
    titles = {str(e["_id"]): e.get("title", "") for e in evs}
    if not titles:
        return {"items": [], "collected": 0.0, "commission_owed": 0.0, "commission_recovered": 0.0,
                "guests": 0, "currency": BASE_CURRENCY}
    orders = await db.orders.find({"ref_id": {"$in": list(titles)}, "gateway": "door",
                                   "payment_status": "paid"}).sort("created_at", -1) \
        .limit(1000).to_list(1000)
    settlements = {s["order_no"]: s for s in
                   await db.vendor_settlements.find({"source": "door_sale"}).limit(1000).to_list(1000)}
    rates = await fx_rates()

    def to_base(amount: float, cur: str) -> float:
        return round(float(amount or 0) / (rates.get((cur or BASE_CURRENCY).upper()) or 1.0), 2)

    items, collected, owed, recovered, guests = [], 0.0, 0.0, 0.0, 0
    for o in orders:
        st = settlements.get(o["order_no"]) or {}
        commission = float(st.get("commission") or 0)
        amount = float(o.get("charge_total") or o["total"])
        cur = o.get("currency", BASE_CURRENCY)
        collected += to_base(amount, cur)
        guests += int(o.get("quantity") or 1)
        if st.get("status") == "paid":
            recovered += to_base(commission, cur)
        else:
            owed += to_base(commission, cur)
        items.append({"order_no": o["order_no"], "event": titles.get(o["ref_id"], o["item_name"]),
                      "guest": o.get("guest_name") or o.get("user_name", ""),
                      "guests": int(o.get("quantity") or 1), "amount": amount,
                      "currency": cur,
                      "method": o.get("payment_method", "cash"), "commission": commission,
                      "settled": st.get("status") == "paid", "at": o.get("paid_at", o["created_at"])})
    return {"items": items, "collected": round(collected, 2), "commission_owed": round(owed, 2),
            "commission_recovered": round(recovered, 2), "guests": guests,
            "currency": BASE_CURRENCY}


@api.get("/partner/events/{event_id}/participants")
async def event_participants(event_id: str, user: dict = Depends(partner_only)):
    ev = await db.events.find_one({"_id": ObjectId(event_id)})
    if not ev or (user["role"] != "admin" and ev.get("partner_id") != user["id"]):
        raise HTTPException(status_code=404, detail="Event not found")
    parts = await db.event_participants.find({"event_id": event_id}).limit(500).to_list(500)
    people = await load_many(db.users, [p["user_id"] for p in parts],
                             {"full_name": 1, "email": 1, "city": 1, "photo": 1})
    out = []
    for p in parts:
        u = people.get(p["user_id"])
        if u:
            item = clean(u)
            item["participation_status"] = p["status"]
            out.append(item)
    return {"items": out}


# ---------------- membership / products / coupons ----------------
@api.get("/plans")
async def plans():
    docs = await db.membership_plans.find({"active": True}).sort([("price", 1)]).limit(50).to_list(50)
    return {"items": [clean(d) for d in docs]}


@api.get("/products")
async def products(city: str = "", country: str = "", q: str = ""):
    flt: dict[str, Any] = {"active": True}
    if city:
        flt["city"] = {"$in": [city, "Global", "All India"]}
    elif country:
        cities = (next((c for c in COUNTRIES if c["name"] == country), {}) or {}).get("cities", [])
        flt["city"] = {"$in": cities + [country, "Global", "All India"]}
    if q:
        flt["name"] = {"$regex": q, "$options": "i"}
    docs = await db.products.find(flt).limit(100).to_list(100)
    return {"items": [clean(d) for d in docs]}


@api.get("/me/membership")
async def my_membership(user: dict = Depends(get_current_user)):
    return {"membership": await membership_active(user["id"])}


@api.get("/me/limits")
async def my_limits(user: dict = Depends(get_current_user)):
    """What the member's current plan allows, and how much of it is left this week."""
    limits = await plan_limits(user["id"])
    left = await messages_left(user["id"], limits)
    return {**limits, "messages_left": left, "messages_unlimited": left is None,
            "week_starts": week_start()}


async def price_for(kind: str, item_id: str):
    if kind == "provider_fee":
        doc = await db.users.find_one({"_id": ObjectId(item_id)}, {"provider": 1})
        p = (doc or {}).get("provider") or {}
        if not p or float(p.get("fee_paid") or 0) > 0:
            return None, 0, "", 0
        return doc, float(p.get("fee") or 0), "Travel provider registration", 0
    if kind == "travel":
        b = await db.travel_bookings.find_one({"_id": ObjectId(item_id)})
        if not b or float(b.get("due_amount") or 0) <= 0:
            return None, 0, "", 0
        return b, float(b["due_amount"]), b.get("item_name", "Travel service"), 0
    if kind == "wallet":
        d = await db.wallet_topups.find_one({"_id": ObjectId(item_id)})
        if not d or d.get("status") != "pending":
            return None, 0, "", 0
        return d, float(d["amount"]), "Buddilio wallet top-up", 0
    if kind == "companion":
        b = await db.companion_bookings.find_one({"_id": ObjectId(item_id)})
        if not b or float(b.get("due_amount") or 0) <= 0:
            return None, 0, "", 0
        # Person-to-person time, not a taxed product — the guest pays exactly the agreed amount.
        return b, float(b["due_amount"]), b.get("item_name", "Hangout booking"), 0
    if kind == "membership":
        d = await db.membership_plans.find_one({"_id": ObjectId(item_id)})
        return (d, d["price"], d["name"], 0) if d else (None, 0, "", 0)
    if kind == "product":
        d = await db.products.find_one({"_id": ObjectId(item_id)})
        if not d:
            return None, 0, "", 0
        base = d["price"] * (1 - d.get("discount_percent", 0) / 100)
        return d, base, d["name"], d.get("tax_percent", 18)
    d = await db.events.find_one({"_id": ObjectId(item_id)})
    return (d, d.get("price", 0), d["title"], 18) if d else (None, 0, "", 0)


@api.post("/checkout")
async def checkout(payload: CheckoutIn, user: dict = Depends(get_current_user)):
    item, base, name, tax_pct = await price_for(payload.kind, payload.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not available")
    subtotal = round(base * max(payload.quantity, 1), 2)
    discount = 0.0
    coupon = None
    member = await membership_active(user["id"])
    if member and member.get("plan_id") and payload.kind in ("product", "event"):
        mp = await db.membership_plans.find_one({"_id": ObjectId(member["plan_id"])})
        if mp and mp.get("discount_percent"):
            discount += round(subtotal * mp["discount_percent"] / 100, 2)
    if payload.coupon_code:
        coupon = await db.coupons.find_one({"code": payload.coupon_code.upper(), "active": True})
        if not coupon:
            raise HTTPException(status_code=400, detail="Invalid coupon code.")
        if coupon.get("expires_at") and coupon["expires_at"] < iso(now_utc()):
            raise HTTPException(status_code=400, detail="This coupon has expired.")
        if subtotal < coupon.get("min_order", 0):
            raise HTTPException(status_code=400,
                                detail=f"Coupon needs a minimum order of {fmt_money(coupon['min_order'])}.")
        if coupon.get("members_only") and not member:
            raise HTTPException(status_code=400, detail="This coupon is for premium members only.")
        used = await db.coupon_usage.count_documents({"code": coupon["code"]})
        if used >= coupon.get("usage_limit", 0):
            raise HTTPException(status_code=400, detail="This coupon has reached its usage limit.")
        discount += round(subtotal * coupon["value"] / 100, 2) if coupon["discount_type"] == "percent" else coupon["value"]
    discount = min(discount, subtotal)

    # The header currency picker is display-only: Buddilio always charges in the base currency.
    currency = BASE_CURRENCY
    rates = await fx_rates()
    tax_pct, tax_label = tax_for(currency, tax_pct, user.get("country_code", ""))
    if payload.kind in ("companion", "wallet", "travel", "provider_fee"):
        # Hangouts are person-to-person time; the guest pays exactly the agreed amount.
        tax_pct, tax_label = 0.0, "No tax"
    taxable = subtotal - discount
    tax = round(taxable * tax_pct / 100, 2)
    total = round(taxable + tax, 2)

    rate = rates[currency]
    override = (item.get("price_overrides") or {}).get(currency)
    if override and currency != BASE_CURRENCY:
        # Admin-set price for this currency wins over the auto-converted amount.
        c_sub = round(float(override) * max(payload.quantity, 1), 2)
        ratio = (c_sub / subtotal) if subtotal else rate
        c_disc = round(discount * ratio, 2)
        c_tax = round((c_sub - c_disc) * tax_pct / 100, 2)
        c_total = round(c_sub - c_disc + c_tax, 2)
        rate = (c_total / total) if total else ratio
    else:
        c_sub, c_disc = round(subtotal * rate, 2), round(discount * rate, 2)
        c_tax, c_total = round(tax * rate, 2), round(total * rate, 2)

    credit, c_credit = 0.0, 0.0
    if payload.use_credit and total > 1:
        bal = await credit_balance(user["id"])
        if bal > 0:
            credit = round(min(bal, total - 1), 2)
            c_credit = round(credit * (c_total / total), 2) if total else 0.0
            total, c_total = round(total - credit, 2), round(c_total - c_credit, 2)

    order = {
        "order_no": "BUD" + uuid.uuid4().hex[:8].upper(), "user_id": user["id"], "user_email": user["email"],
        "kind": payload.kind, "ref_id": payload.item_id, "item_name": name, "quantity": payload.quantity,
        "subtotal": subtotal, "discount": discount, "tax": tax, "total": total,
        "tax_percent": tax_pct, "tax_label": tax_label,
        "credit_applied": credit, "charge_credit": c_credit,
        "coupon": coupon["code"] if coupon else "", "currency": currency, "fx_rate": rate,
        "base_currency": BASE_CURRENCY, "charge_subtotal": c_sub, "charge_discount": c_disc,
        "charge_tax": c_tax, "charge_total": c_total,
        "payment_status": "pending", "order_status": "created", "refund_status": "none",
        "gateway": "razorpay_sim" if currency == "INR" else "stripe",
        "transaction_id": "", "created_at": iso(now_utc()),
    }
    res = await db.orders.insert_one(order)
    return {"order": clean(await db.orders.find_one({"_id": res.inserted_id})),
            "credit_balance": await credit_balance(user["id"])}


async def mark_failed(order: dict, reason: str = ""):
    if order.get("payment_status") == "failed":
        return
    await db.orders.update_one({"_id": order["_id"]},
                               {"$set": {"payment_status": "failed", "order_status": "failed",
                                         "failure_reason": reason}})
    await db.payments.insert_one({"order_id": str(order["_id"]), "user_id": order["user_id"],
                                  "amount": order["total"], "status": "failed", "reason": reason,
                                  "created_at": iso(now_utc())})


async def vendor_snapshot_hook(order: dict):
    """Freeze the vendor's commercial terms onto the paid booking, when the vendor has a schedule."""
    try:
        import vendor_routes
        await vendor_routes.snapshot_booking(order)
    except Exception as exc:                                     # never block fulfilment
        logger.warning(f"commercial snapshot skipped for {order.get('order_no')}: {exc}")


async def fulfil_order(order: dict, txn: str, gateway: str = "razorpay_sim") -> dict:
    """Single source of truth for post-payment fulfilment. Idempotent."""
    if order["payment_status"] == "paid":
        return clean(order)
    uid = order["user_id"]
    await db.orders.update_one({"_id": order["_id"]},
                               {"$set": {"payment_status": "paid", "order_status": "completed",
                                         "transaction_id": txn, "gateway": gateway,
                                         "paid_at": iso(now_utc())}})
    await db.payments.insert_one({"order_id": str(order["_id"]), "user_id": uid,
                                  "amount": order["total"], "status": "captured", "gateway": gateway,
                                  "transaction_id": txn, "created_at": iso(now_utc())})
    if order.get("coupon"):
        await db.coupon_usage.insert_one({"code": order["coupon"], "user_id": uid,
                                          "order_id": str(order["_id"]), "created_at": iso(now_utc())})
    await vendor_snapshot_hook(order)
    if order.get("credit_applied", 0) > 0:
        await db.credits.update_one(
            {"order_id": str(order["_id"]), "type": "spent"},
            {"$setOnInsert": {"user_id": uid, "amount": -float(order["credit_applied"]), "type": "spent",
                              "reason": f"Credit applied to order #{order['order_no']}",
                              "order_id": str(order["_id"]), "created_at": iso(now_utc())}},
            upsert=True)
    await award_referral(uid, order)
    await issue_pass(order)
    receipt = (f"<p><b>{order['item_name']}</b></p>"
               f"<p>Order <b>#{order['order_no']}</b><br/>Amount paid: "
               f"<b>{fmt_money(order.get('charge_total', order['total']), order.get('currency'))}</b>"
               f" (incl. {fmt_money(order.get('charge_tax', order['tax']), order.get('currency'))}"
               f" {order.get('tax_label', 'tax')})<br/>Payment ID: {txn}</p>")

    if order["kind"] == "membership":
        plan = await db.membership_plans.find_one({"_id": ObjectId(order["ref_id"])})
        await db.user_memberships.update_many({"user_id": uid, "status": "active"},
                                              {"$set": {"status": "replaced"}})
        ends = now_utc() + timedelta(days=plan.get("duration_days", 365))
        await db.user_memberships.insert_one({
            "user_id": uid, "plan_id": order["ref_id"], "plan_name": plan["name"],
            "status": "active", "starts_at": iso(now_utc()), "ends_at": iso(ends),
            "order_id": str(order["_id"]), "created_at": iso(now_utc())})
        await notify(uid, "Membership activated",
                     f"Your {plan['name']} membership is active until {ends.strftime('%d %b %Y')}.",
                     "membership", "/membership", email=False)
        u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1})
        if u:
            await send_tpl("membership_active", u["email"], {
                "plan_name": plan["name"], "receipt": receipt,
                "valid_until": ends.strftime("%d %b %Y"),
                "membership_url": f"{FRONTEND_URL}/membership"})
    elif order["kind"] == "travel":
        await fulfil_travel(order, uid)
    elif order["kind"] == "provider_fee":
        await fulfil_provider_fee(order, uid)
    elif order["kind"] == "wallet":
        await fulfil_topup(order, uid)
    elif order["kind"] == "companion":
        await fulfil_companion(order, uid)
    elif order["kind"] == "event":
        ev = await db.events.find_one({"_id": ObjectId(order["ref_id"])})
        part = await db.event_participants.find_one({"event_id": order["ref_id"], "user_id": uid})
        if ev and not part:
            st = "confirmed" if ev.get("approval_mode") == "instant" else "pending"
            await db.event_participants.insert_one({"event_id": order["ref_id"], "user_id": uid,
                                                     "status": st, "order_id": str(order["_id"]),
                                                     "created_at": iso(now_utc())})
            await db.events.update_one({"_id": ev["_id"]}, {"$inc": {"participant_count": 1}})
            if st == "confirmed":
                await ensure_event_chat(order["ref_id"], uid)
        elif part and part.get("status") == "confirmed":
            await db.event_participants.update_one({"_id": part["_id"]}, {"$set": {"order_id": str(order["_id"])}})
            await ensure_event_chat(order["ref_id"], uid)
        await notify(uid, "Event pass confirmed", f"You're going to {order['item_name']}!",
                     "event", f"/events/{order['ref_id']}", email=False)
        u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1})
        if u and ev:
            starts = datetime.fromisoformat(ev["starts_at"])
            await send_tpl("booking_confirmed", u["email"], {
                "event_title": ev["title"], "receipt": receipt,
                "when": starts.strftime("%a %d %b %Y, %I:%M %p"), "venue": ev.get("venue", ""),
                "city": ev["city"], "host": ev.get("partner_name", "Buddilio"),
                "cancellation": ev.get("cancellation_policy", ""),
                "event_url": f"{FRONTEND_URL}/events/{order['ref_id']}"})
    else:
        await notify(uid, "Purchase successful", f"{order['item_name']} is now in your account.",
                     "order", "/orders", email=False)
        u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1})
        if u:
            await send_tpl("purchase_confirmed", u["email"],
                           {"receipt": receipt, "orders_url": f"{FRONTEND_URL}/orders"})
    return clean(await db.orders.find_one({"_id": order["_id"]}))


@api.get("/payments/config")
async def payment_config():
    kid = os.environ.get("RAZORPAY_KEY_ID", "")
    conf = await currency_config()
    return {"razorpay_live": bool(kid and razorpay_client()), "razorpay_key_id": kid,
            "paypal_enabled": paypal.enabled(), "paypal_currency": paypal.CURRENCY,
            "subscriptions_via": "paypal" if paypal.enabled() else "",
            "stripe_enabled": bool(os.environ.get("STRIPE_API_KEY")),
            "simulation_enabled": (not (razorpay_client() or os.environ.get("STRIPE_API_KEY")
                                        or paypal.enabled()))
            and os.environ.get("ALLOW_SIMULATED_PAYMENTS", "").lower() in ("1", "true", "yes"),
            "base_currency": BASE_CURRENCY, "currencies": [{"code": k, **v} for k, v in conf.items()],
            "methods": {"INR": ["upi", "card", "netbanking", "wallet"], "other": ["card"]}}


def stripe_checkout_client(request: Request):
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    key = os.environ.get("STRIPE_API_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="International payments are not configured yet.")
    return StripeCheckout(api_key=key, webhook_url=f"{str(request.base_url)}api/webhook/stripe")


@api.post("/payments/stripe/session")
async def create_stripe_session(body: dict, request: Request, user: dict = Depends(get_current_user)):
    from emergentintegrations.payments.stripe.checkout import CheckoutSessionRequest
    order = await db.orders.find_one({"_id": ObjectId(body.get("order_id")), "user_id": user["id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["payment_status"] == "paid":
        raise HTTPException(status_code=400, detail="This order is already paid.")
    origin = (body.get("origin_url") or FRONTEND_URL).rstrip("/")
    client_sc = stripe_checkout_client(request)
    amount = float(order.get("charge_total") or order["total"])
    req = CheckoutSessionRequest(
        amount=amount, currency=order.get("currency", "INR").lower(),
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"order_id": str(order["_id"]), "user_id": user["id"], "kind": order["kind"]})
    try:
        session = await client_sc.create_checkout_session(req)
    except Exception as e:
        logger.error(f"Stripe session failed: {e}")
        raise HTTPException(status_code=502, detail="Could not open the payment window. Please try again.")
    await db.payment_transactions.insert_one({
        "session_id": session.session_id, "order_id": str(order["_id"]), "user_id": user["id"],
        "amount": amount, "currency": order.get("currency", "INR"), "status": "initiated",
        "payment_status": "pending", "created_at": iso(now_utc()), "updated_at": iso(now_utc())})
    await db.orders.update_one({"_id": order["_id"]},
                               {"$set": {"gateway": "stripe", "gateway_order_id": session.session_id}})
    return {"checkout_url": session.url, "session_id": session.session_id}


async def settle_stripe_session(session_id: str, payment_status: str, txn: str = ""):
    rec = await db.payment_transactions.find_one({"session_id": session_id})
    if not rec:
        return None
    if payment_status == "paid" and rec.get("payment_status") != "paid":
        await db.payment_transactions.update_one(
            {"session_id": session_id, "payment_status": {"$ne": "paid"}},
            {"$set": {"status": "completed", "payment_status": "paid", "transaction_id": txn,
                      "updated_at": iso(now_utc())}})
        order = await db.orders.find_one({"_id": ObjectId(rec["order_id"])})
        if order:
            await fulfil_order(order, txn or session_id, "stripe")
    elif payment_status in ("failed", "expired") and rec.get("payment_status") != "paid":
        await db.payment_transactions.update_one({"session_id": session_id},
                                                 {"$set": {"status": payment_status,
                                                           "payment_status": payment_status,
                                                           "updated_at": iso(now_utc())}})
        order = await db.orders.find_one({"_id": ObjectId(rec["order_id"])})
        if order:
            await mark_failed(order, f"stripe {payment_status}")
    return await db.payment_transactions.find_one({"session_id": session_id})


@api.get("/payments/status/{session_id}")
async def stripe_status(session_id: str, request: Request):
    rec = await db.payment_transactions.find_one({"session_id": session_id})
    if not rec:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if rec.get("payment_status") != "paid":
        try:
            status = await stripe_checkout_client(request).get_checkout_status(session_id)
            if status.payment_status == "paid" or status.status == "complete":
                rec = await settle_stripe_session(session_id, "paid", session_id)
            elif status.status == "expired":
                rec = await settle_stripe_session(session_id, "expired")
        except HTTPException:
            raise
        except Exception as e:
            logger.info(f"stripe status poll: {e}")
    return {"session_id": session_id, "status": rec.get("status"), "payment_status": rec.get("payment_status")}


@app.post("/api/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    try:
        res = await stripe_checkout_client(request).handle_webhook(body, request.headers.get("Stripe-Signature"))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Rejected Stripe webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    await db.webhook_events.insert_one({"source": "stripe", "event": res.event_type,
                                        "session_id": res.session_id, "received_at": iso(now_utc())})
    if res.payment_status == "paid":
        await settle_stripe_session(res.session_id, "paid", res.session_id)
    elif res.event_type in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        await settle_stripe_session(res.session_id, "failed")
    return {"status": "ok"}


class PayPalOrderIn(BaseModel):
    order_id: str
    origin_url: str = ""
    paypal_order_id: str = ""


class PayPalSubIn(BaseModel):
    plan_id: str
    origin_url: str = ""


class PayPalActivateIn(BaseModel):
    subscription_id: str


def as_oid(value: str, label: str = "record") -> ObjectId:
    if not ObjectId.is_valid(value or ""):
        raise HTTPException(status_code=400, detail=f"That {label} id is not valid.")
    return ObjectId(value)


@api.get("/payments/paypal/config")
async def paypal_config():
    return {"enabled": paypal.enabled(), "currency": paypal.CURRENCY,
            "env": os.environ.get("PAYPAL_ENV", "sandbox")}


async def paypal_usd(order: dict) -> float:
    """PayPal charges in USD; convert from the order's base amount when needed."""
    if order.get("currency") == paypal.CURRENCY:
        return round(float(order.get("charge_total") or order["total"]), 2)
    rates = await fx_rates()
    return max(round(float(order["total"]) * float(rates.get(paypal.CURRENCY, 0.012)), 2), 1.0)


@api.post("/payments/paypal/order")
async def create_paypal_order(body: PayPalOrderIn, user: dict = Depends(get_current_user)):
    if not paypal.enabled():
        raise HTTPException(status_code=400, detail="PayPal isn't configured yet.")
    order = await db.orders.find_one({"_id": as_oid(body.order_id, "order"), "user_id": user["id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    if order["payment_status"] == "paid":
        raise HTTPException(status_code=400, detail="This order is already paid.")
    origin = (body.origin_url or FRONTEND_URL).rstrip("/")
    amount = await paypal_usd(order)
    try:
        res = await paypal.create_order(
            amount, str(order["_id"]), order.get("item_name", "Buddilio order"),
            f"{origin}/payments/paypal/return?order={order['_id']}",
            f"{origin}/checkout?kind={order['kind']}&id={order.get('ref_id', '')}")
    except paypal.PayPalError as exc:
        raise HTTPException(status_code=502, detail=paypal.message_of(exc))
    await db.orders.update_one({"_id": order["_id"]}, {"$set": {
        "gateway": "paypal", "gateway_order_id": res["id"],
        "charge_currency_paypal": paypal.CURRENCY, "charge_total_paypal": amount}})
    return {"paypal_order_id": res["id"], "approve_url": paypal.approve_link(res),
            "amount": amount, "currency": paypal.CURRENCY}


@api.post("/payments/paypal/capture")
async def capture_paypal_order(body: PayPalOrderIn, user: dict = Depends(get_current_user)):
    order = await db.orders.find_one({"_id": as_oid(body.order_id, "order"), "user_id": user["id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    if order["payment_status"] == "paid":
        return {"order": clean(order), "already": True}
    pp_id = body.paypal_order_id or order.get("gateway_order_id", "")
    try:
        res = await paypal.capture_order(pp_id)
    except paypal.PayPalError as exc:
        await mark_failed(order, f"paypal {paypal.message_of(exc)}")
        raise HTTPException(status_code=400, detail=paypal.member_message(exc))
    if res.get("status") != "COMPLETED":
        await mark_failed(order, f"paypal {res.get('status')}")
        raise HTTPException(status_code=400, detail="PayPal did not complete this payment.")
    cap = (((res.get("purchase_units") or [{}])[0].get("payments") or {}).get("captures") or [{}])[0]
    return {"order": await fulfil_order(order, cap.get("id") or pp_id, "paypal")}


# ---- PayPal subscriptions (memberships) ----
async def paypal_plan_for(plan: dict) -> str:
    """Creates the PayPal product + billing plan once per membership plan, then reuses it."""
    days = int(plan.get("duration_days") or 365)
    interval, count = ("YEAR", 1) if days >= 300 else ("MONTH", max(round(days / 30), 1))
    rates = await fx_rates()
    usd = round(float(plan.get("price_usd") or float(plan["price"]) * float(rates.get(paypal.CURRENCY, 0.012))), 2)
    saved = plan.get("paypal") or {}
    env = os.environ.get("PAYPAL_ENV", "sandbox").lower()
    if (saved.get("plan_id") and saved.get("price") == usd and saved.get("interval") == interval
            and saved.get("env") == env):
        return saved["plan_id"]
    product_id = saved.get("product_id") if saved.get("env") == env else ""
    product_id = product_id or await paypal.ensure_product(
        f"Buddilio {plan['name']}", plan.get("description", "Buddilio membership"))
    plan_id = await paypal.create_plan(product_id, plan["name"], usd, interval, count)
    await db.membership_plans.update_one({"_id": plan["_id"]}, {"$set": {"paypal": {
        "product_id": product_id, "plan_id": plan_id, "price": usd, "interval": interval,
        "interval_count": count, "env": env, "created_at": iso(now_utc())}}})
    return plan_id


@api.post("/payments/paypal/subscription")
async def start_paypal_subscription(body: PayPalSubIn, user: dict = Depends(get_current_user)):
    if not paypal.enabled():
        raise HTTPException(status_code=400, detail="PayPal isn't configured yet.")
    plan = await db.membership_plans.find_one({"_id": as_oid(body.plan_id, "plan"), "active": True})
    if not plan:
        raise HTTPException(status_code=404, detail="That membership plan isn't available.")
    origin = (body.origin_url or FRONTEND_URL).rstrip("/")
    try:
        pp_plan = await paypal_plan_for(plan)
        res = await paypal.create_subscription(
            pp_plan, user["email"], user.get("full_name", ""),
            f"{origin}/payments/paypal/subscription-return",
            f"{origin}/membership", custom_id=user["id"])
    except paypal.PayPalError as exc:
        raise HTTPException(status_code=502, detail=paypal.message_of(exc))
    await db.paypal_subscriptions.update_one({"subscription_id": res["id"]}, {"$set": {
        "subscription_id": res["id"], "user_id": user["id"], "plan_id": str(plan["_id"]),
        "plan_name": plan["name"], "paypal_plan_id": pp_plan, "status": res.get("status", "APPROVAL_PENDING"),
        "created_at": iso(now_utc())}}, upsert=True)
    return {"subscription_id": res["id"], "approve_url": paypal.approve_link(res)}


async def activate_paypal_membership(subscription_id: str) -> dict:
    """Turns an approved PayPal subscription into an active Buddilio membership. Idempotent."""
    sub = await db.paypal_subscriptions.find_one({"subscription_id": subscription_id})
    if not sub:
        raise HTTPException(status_code=404, detail="We couldn't find that subscription.")
    try:
        live = await paypal.get_subscription(subscription_id)
    except paypal.PayPalError as exc:
        raise HTTPException(status_code=502, detail=paypal.message_of(exc))
    status = live.get("status", "")
    await db.paypal_subscriptions.update_one({"_id": sub["_id"]}, {"$set": {
        "status": status, "synced_at": iso(now_utc()),
        "next_billing": (live.get("billing_info") or {}).get("next_billing_time", "")}})
    if status not in ("ACTIVE", "APPROVED"):
        return {"status": status, "membership": None}
    plan = await db.membership_plans.find_one({"_id": ObjectId(sub["plan_id"])})
    uid = sub["user_id"]
    existing = await db.user_memberships.find_one({"paypal_subscription_id": subscription_id,
                                                  "status": "active"})
    if existing:
        return {"status": status, "membership": clean(existing)}
    amount = float(((live.get("billing_info") or {}).get("last_payment") or {})
                   .get("amount", {}).get("value") or (plan.get("paypal") or {}).get("price") or 0)
    order = {"order_no": "BUD" + uuid.uuid4().hex[:8].upper(), "user_id": uid,
             "user_email": sub.get("user_email", ""), "kind": "membership", "ref_id": sub["plan_id"],
             "item_name": f"{plan['name']} membership", "quantity": 1,
             "subtotal": amount, "discount": 0.0, "tax": 0.0, "total": amount,
             "tax_percent": 0.0, "tax_label": "No tax", "credit_applied": 0.0, "charge_credit": 0.0,
             "coupon": "", "currency": paypal.CURRENCY, "fx_rate": 1.0,
             "base_currency": paypal.CURRENCY, "charge_subtotal": amount, "charge_discount": 0.0,
             "charge_tax": 0.0, "charge_total": amount,
             "payment_status": "pending", "order_status": "created", "refund_status": "none",
             "gateway": "paypal", "gateway_order_id": subscription_id, "transaction_id": "",
             "created_at": iso(now_utc())}
    res = await db.orders.insert_one(order)
    saved = await db.orders.find_one({"_id": res.inserted_id})
    await fulfil_order(saved, subscription_id, "paypal")
    await db.user_memberships.update_one(
        {"order_id": str(res.inserted_id)},
        {"$set": {"paypal_subscription_id": subscription_id, "auto_renews": True}})
    member = await db.user_memberships.find_one({"order_id": str(res.inserted_id)})
    return {"status": status, "membership": clean(member) if member else None}


@api.post("/payments/paypal/subscription/activate")
async def confirm_paypal_subscription(body: PayPalActivateIn, user: dict = Depends(get_current_user)):
    sub = await db.paypal_subscriptions.find_one({"subscription_id": body.subscription_id,
                                                  "user_id": user["id"]})
    if not sub:
        raise HTTPException(status_code=404, detail="We couldn't find that subscription.")
    return await activate_paypal_membership(sub["subscription_id"])


@api.post("/me/membership/cancel")
async def cancel_my_membership(user: dict = Depends(get_current_user)):
    member = await membership_active(user["id"])
    if not member:
        raise HTTPException(status_code=400, detail="You don't have an active membership.")
    sub_id = member.get("paypal_subscription_id", "")
    if sub_id:
        try:
            await paypal.cancel_subscription(sub_id, "Cancelled from the Buddilio membership page")
        except paypal.PayPalError as exc:
            raise HTTPException(status_code=502, detail=paypal.message_of(exc))
        await db.paypal_subscriptions.update_one({"subscription_id": sub_id},
                                                {"$set": {"status": "CANCELLED",
                                                          "cancelled_at": iso(now_utc())}})
    await db.user_memberships.update_one({"_id": ObjectId(member["id"])}, {"$set": {
        "auto_renews": False, "cancelled_at": iso(now_utc())}})
    return {"ok": True, "ends_at": member.get("ends_at", ""),
            "message": "Auto-renewal is off. Your benefits stay active until the end of the paid period."}


async def paypal_webhook_id() -> str:
    """Env wins; otherwise the id created from Admin -> Payments is stored in settings."""
    if os.environ.get("PAYPAL_WEBHOOK_ID"):
        return os.environ["PAYPAL_WEBHOOK_ID"]
    s = await db.settings.find_one({}, {"paypal_webhook_id": 1}) or {}
    return s.get("paypal_webhook_id", "")


def paypal_webhook_url() -> str:
    return f"{FRONTEND_URL.rstrip('/')}/api/webhook/paypal"


@api.get("/admin/paypal/webhook")
async def paypal_webhook_status(user: dict = Depends(require_perm("finance:manage"))):
    wanted = paypal_webhook_url()
    out = {"env": os.environ.get("PAYPAL_ENV", "sandbox"), "url": wanted,
           "webhook_id": await paypal_webhook_id(), "from_env": bool(os.environ.get("PAYPAL_WEBHOOK_ID")),
           "events": paypal.WEBHOOK_EVENTS, "registered": [], "matches": False, "error": ""}
    if not paypal.enabled():
        out["error"] = "PayPal keys are not configured."
        return out
    try:
        hooks = await paypal.list_webhooks()
    except paypal.PayPalError as exc:
        out["error"] = paypal.message_of(exc)
        return out
    out["registered"] = [{"id": h.get("id"), "url": h.get("url"),
                          "events": [e.get("name") for e in h.get("event_types", [])]} for h in hooks]
    out["matches"] = any(h.get("url") == wanted and h.get("id") == out["webhook_id"] for h in hooks)
    return out


@api.post("/admin/paypal/webhook/setup")
async def paypal_webhook_setup(user: dict = Depends(require_perm("finance:manage"))):
    """Creates (or reuses) the PayPal webhook for this site and stores its id."""
    if not paypal.enabled():
        raise HTTPException(status_code=400, detail="PayPal keys are not configured.")
    wanted = paypal_webhook_url()
    try:
        hooks = await paypal.list_webhooks()
        existing = next((h for h in hooks if h.get("url") == wanted), None)
        if existing:
            await paypal.replace_webhook_events(existing["id"])
            hook_id, created = existing["id"], False
        else:
            hook_id, created = (await paypal.create_webhook(wanted))["id"], True
    except paypal.PayPalError as exc:
        raise HTTPException(status_code=502, detail=paypal.message_of(exc))
    s = await db.settings.find_one({})
    await db.settings.update_one({"_id": s["_id"]}, {"$set": {"paypal_webhook_id": hook_id}})
    await audit(user, "paypal.webhook_setup", "settings", str(s["_id"]),
                {"webhook_id": hook_id, "url": wanted, "created": created})
    logger.info(f"paypal webhook {'created' if created else 'reused'}: {hook_id} -> {wanted}")
    return {"webhook_id": hook_id, "url": wanted, "created": created,
            "events": paypal.WEBHOOK_EVENTS,
            "message": ("Webhook created — renewals and cancellations now update on their own."
                        if created else "Webhook already existed; its event list was refreshed.")}


@app.post("/api/webhook/paypal")
async def paypal_webhook(request: Request):
    body = await request.json()
    event = body.get("event_type", "")
    resource = body.get("resource") or {}
    webhook_id = await paypal_webhook_id()
    if not webhook_id:
        # Fail closed: without a webhook id we cannot prove PayPal sent this, so never fulfil on it.
        logger.warning(f"paypal webhook {event} ignored — PAYPAL_WEBHOOK_ID not configured")
        return {"status": "unverified"}
    if not await paypal.verify_webhook(request.headers, body, webhook_id):
        logger.warning(f"paypal webhook {event} failed signature verification")
        return {"status": "invalid"}
    try:
        if event in ("BILLING.SUBSCRIPTION.ACTIVATED", "PAYMENT.SALE.COMPLETED",
                     "BILLING.SUBSCRIPTION.UPDATED"):
            sub_id = resource.get("id") if event.startswith("BILLING") else resource.get("billing_agreement_id")
            if sub_id:
                await activate_paypal_membership(sub_id)
        elif event in ("BILLING.SUBSCRIPTION.CANCELLED", "BILLING.SUBSCRIPTION.EXPIRED",
                       "BILLING.SUBSCRIPTION.SUSPENDED"):
            sub_id = resource.get("id", "")
            await db.paypal_subscriptions.update_one({"subscription_id": sub_id},
                                                    {"$set": {"status": event.rsplit(".", 1)[-1]}})
            await db.user_memberships.update_many({"paypal_subscription_id": sub_id},
                                                  {"$set": {"auto_renews": False}})
        elif event == "PAYMENT.CAPTURE.COMPLETED":
            ref = resource.get("custom_id", "")
            capture_id = resource.get("id", "")
            if ref and ObjectId.is_valid(ref) and capture_id:
                order = await db.orders.find_one({"_id": ObjectId(ref)})
                if order and order["payment_status"] != "paid":
                    # Confirm the capture with PayPal itself before releasing anything.
                    pp = await paypal.get_order(order.get("gateway_order_id", ""))
                    if pp.get("status") == "COMPLETED":
                        await fulfil_order(order, capture_id, "paypal")
                    else:
                        logger.warning(f"paypal capture {capture_id} not COMPLETED at PayPal — skipped")
    except Exception as exc:
        logger.warning(f"paypal webhook {event} handling failed: {exc}")
    return {"status": "ok"}


@api.post("/payments/razorpay/order")
async def create_razorpay_order(body: dict, user: dict = Depends(get_current_user)):
    client_rp = razorpay_client()
    if not client_rp:
        raise HTTPException(status_code=503, detail="Online payments are not configured yet.")
    order = await db.orders.find_one({"_id": ObjectId(body.get("order_id")), "user_id": user["id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["payment_status"] == "paid":
        raise HTTPException(status_code=400, detail="This order is already paid.")
    try:
        rp = await asyncio.to_thread(client_rp.order.create, {
            "amount": int(round(order["total"] * 100)), "currency": "INR",
            "receipt": order["order_no"][:40], "payment_capture": 1,
            "notes": {"buddilio_order": str(order["_id"]), "kind": order["kind"]}})
    except Exception as e:
        logger.error(f"Razorpay order create failed: {e}")
        raise HTTPException(status_code=502, detail="Could not reach the payment gateway. Please try again.")
    await db.orders.update_one({"_id": order["_id"]},
                               {"$set": {"gateway": "razorpay", "gateway_order_id": rp["id"]}})
    return {"razorpay_order_id": rp["id"], "amount": rp["amount"], "currency": rp["currency"],
            "key_id": os.environ["RAZORPAY_KEY_ID"], "order_no": order["order_no"]}


@api.post("/payments/razorpay/verify")
async def verify_razorpay(body: dict, user: dict = Depends(get_current_user)):
    client_rp = razorpay_client()
    if not client_rp:
        raise HTTPException(status_code=503, detail="Online payments are not configured yet.")
    order = await db.orders.find_one({"_id": ObjectId(body.get("order_id")), "user_id": user["id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        client_rp.utility.verify_payment_signature({
            "razorpay_order_id": body.get("razorpay_order_id"),
            "razorpay_payment_id": body.get("razorpay_payment_id"),
            "razorpay_signature": body.get("razorpay_signature")})
    except Exception:
        await mark_failed(order, "signature verification failed")
        raise HTTPException(status_code=400, detail="We could not verify this payment. You have not been charged.")
    try:
        payment = await asyncio.to_thread(client_rp.payment.fetch, body.get("razorpay_payment_id"))
    except Exception:
        raise HTTPException(status_code=502, detail="Could not confirm payment with the gateway. Please contact support.")
    if payment.get("status") not in ("captured", "authorized"):
        await mark_failed(order, payment.get("error_description") or payment.get("status", "failed"))
        raise HTTPException(status_code=402, detail="Payment did not go through. No amount was captured.")
    if int(payment.get("amount", 0)) != int(round(order["total"] * 100)):
        await mark_failed(order, "amount mismatch")
        raise HTTPException(status_code=400, detail="Payment amount did not match the order. Please contact support.")
    out = await fulfil_order(order, payment["id"], "razorpay")
    return {"status": "paid", "order": out, "method": payment.get("method")}


@app.post("/api/payments/razorpay/webhook")
async def razorpay_webhook(request: Request):
    client_rp = razorpay_client()
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    raw = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not client_rp or not secret:
        raise HTTPException(status_code=503, detail="Webhooks are not configured.")
    try:
        client_rp.utility.verify_webhook_signature(raw.decode(), signature, secret)
    except Exception:
        logger.warning("Rejected Razorpay webhook with invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    body = await request.json()
    event = body.get("event", "")
    entity = (body.get("payload", {}).get("payment", {}) or {}).get("entity", {})
    await db.webhook_events.insert_one({"event": event, "payment_id": entity.get("id"),
                                        "received_at": iso(now_utc())})
    internal_id = (entity.get("notes") or {}).get("buddilio_order")
    order = None
    if internal_id:
        order = await db.orders.find_one({"_id": ObjectId(internal_id)})
    elif entity.get("order_id"):
        order = await db.orders.find_one({"gateway_order_id": entity["order_id"]})
    if not order:
        return {"status": "ignored"}
    if event in ("payment.captured", "payment.authorized"):
        await fulfil_order(order, entity.get("id", ""), "razorpay")
    elif event == "payment.failed":
        await mark_failed(order, entity.get("error_description", "gateway reported failure"))
    elif event.startswith("refund."):
        await db.orders.update_one({"_id": order["_id"]},
                                   {"$set": {"refund_status": "refunded", "order_status": "refunded",
                                             "refunded_at": iso(now_utc())}})
    return {"status": "processed"}


@api.post("/payments/verify")
async def verify_payment(payload: VerifyPaymentIn, user: dict = Depends(get_current_user)):
    """Simulation path — only allowed when NO real gateway is configured and it's explicitly enabled."""
    real_gateway = bool(razorpay_client() or os.environ.get("STRIPE_API_KEY") or paypal.enabled())
    if real_gateway or os.environ.get("ALLOW_SIMULATED_PAYMENTS", "").lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=400,
                            detail="Simulated payments are disabled. Please pay with a real payment method.")
    order = await db.orders.find_one({"_id": ObjectId(payload.order_id), "user_id": user["id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["payment_status"] == "paid":
        return {"status": "paid", "order": clean(order)}
    if payload.simulate == "failure":
        await mark_failed(order, "simulated failure")
        raise HTTPException(status_code=402, detail="Payment failed. No amount was charged. Please try again.")
    txn = payload.gateway_payment_id or "pay_" + uuid.uuid4().hex[:14]
    out = await fulfil_order(order, txn, "razorpay_sim")
    return {"status": "paid", "order": out}


async def issue_pass(order: dict) -> dict | None:
    """Issues the QR voucher for a paid booking. One pass per order, idempotent."""
    if order["kind"] not in ("event", "product", "hangout", "travel"):
        return None
    existing = await db.passes.find_one({"order_id": str(order["_id"])})
    if existing:
        return clean(existing)
    user = None
    if ObjectId.is_valid(order.get("user_id") or ""):
        user = await db.users.find_one({"_id": ObjectId(order["user_id"])}, {"full_name": 1, "email": 1})
    city, starts_at, vendor_name = "", "", ""
    if order["kind"] == "event" and ObjectId.is_valid(order.get("ref_id", "")):
        ev = await db.events.find_one({"_id": ObjectId(order["ref_id"])},
                                      {"city": 1, "starts_at": 1, "partner_name": 1, "venue": 1})
        if ev:
            city = ev.get("venue") or ev.get("city", "")
            starts_at = ev.get("starts_at", "")
            vendor_name = ev.get("partner_name", "")
    for attempt in range(6):
        code = passes.new_code()
        if not await db.passes.find_one({"code": code}):
            break
    doc = {"code": code, "order_id": str(order["_id"]), "order_no": order["order_no"],
           "user_id": order["user_id"],
           "user_name": (user.get("full_name", "") if user else order.get("guest_name", "")),
           "kind": order["kind"], "ref_id": order.get("ref_id", ""), "item_name": order["item_name"],
           "quantity": order.get("quantity", 1), "city": city, "starts_at": starts_at,
           "vendor_name": vendor_name,
           "amount_label": fmt_money(order.get("charge_total", order["total"]), order.get("currency")),
           "status": "valid", "redeemed_at": "", "redeemed_by": "", "redeemed_by_name": "",
           "created_at": iso(now_utc())}
    res = await db.passes.insert_one(doc)
    return clean(await db.passes.find_one({"_id": res.inserted_id}))


def pass_verify_url(code: str) -> str:
    return f"{FRONTEND_URL.rstrip('/')}/verify/{code}"


@api.post("/admin/passes/backfill")
async def backfill_passes(user: dict = Depends(require_perm("finance:manage"))):
    """Issues passes for paid bookings made before passes existed."""
    made = 0
    rows = await db.orders.find({"payment_status": "paid",
                                 "kind": {"$in": ["event", "product", "hangout", "travel"]}}) \
        .limit(2000).to_list(2000)
    for order in rows:
        if await issue_pass(order):
            made += 1
    return {"checked": len(rows), "passes": await db.passes.count_documents({}), "issued_now": made}


@api.get("/me/passes")
async def my_passes(user: dict = Depends(get_current_user)):
    rows = await db.passes.find({"user_id": user["id"]}).sort("created_at", -1).limit(100).to_list(100)
    return {"items": [clean(r) for r in rows]}


@api.get("/passes/{code}/qr.png")
async def pass_qr(code: str):
    doc = await db.passes.find_one({"code": code.upper()})
    if not doc:
        raise HTTPException(status_code=404, detail="That pass code doesn't exist.")
    return Response(content=passes.qr_png(pass_verify_url(doc["code"])), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@api.get("/passes/{code}/pdf")
async def pass_pdf_download(code: str, user: dict = Depends(get_current_user)):
    doc = await db.passes.find_one({"code": code.upper()})
    if not doc:
        raise HTTPException(status_code=404, detail="That pass code doesn't exist.")
    if doc["user_id"] != user["id"] and "finance:view" not in perms_of(user):
        raise HTTPException(status_code=403, detail="That pass isn't yours.")
    pdf = passes.pass_pdf(clean(doc), pass_verify_url(doc["code"]))
    return Response(content=bytes(pdf), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{doc["code"]}.pdf"'})


@api.get("/passes/{code}/check")
async def check_pass(code: str):
    """Public read-only check — shows validity without exposing personal details."""
    doc = await db.passes.find_one({"code": code.upper()})
    if not doc:
        return {"found": False}
    return {"found": True, "code": doc["code"], "status": doc["status"], "kind": doc["kind"],
            "item_name": doc["item_name"], "quantity": doc.get("quantity", 1),
            "guest_initials": "".join(p[0] for p in (doc.get("user_name") or "G").split()[:2]).upper(),
            "city": doc.get("city", ""), "starts_at": doc.get("starts_at", ""),
            "vendor_name": doc.get("vendor_name", ""), "redeemed_at": doc.get("redeemed_at", ""),
            "redeemed_by_name": doc.get("redeemed_by_name", "")}


@api.post("/passes/{code}/redeem")
async def redeem_pass(code: str, user: dict = Depends(get_current_user)):
    """Anyone signed in — organiser, host or companion — can redeem, once."""
    doc = await db.passes.find_one({"code": code.upper()})
    if not doc:
        raise HTTPException(status_code=404, detail="We couldn't find that code. Check it and try again.")
    if doc["status"] == "redeemed":
        raise HTTPException(status_code=400,
                            detail=f"Already used on {str(doc.get('redeemed_at'))[:16].replace('T', ' ')}"
                                   f" by {doc.get('redeemed_by_name') or 'someone'}.")
    if doc["status"] != "valid":
        raise HTTPException(status_code=400, detail=f"This pass is {doc['status']} and can't be used.")
    order = None
    if ObjectId.is_valid(doc.get("order_id") or ""):
        order = await db.orders.find_one({"_id": ObjectId(doc["order_id"])})
    if not order:
        raise HTTPException(status_code=400, detail="This pass has no valid booking behind it.")
    if order["payment_status"] != "paid" or order.get("refund_status") in ("refunded", "partial"):
        await db.passes.update_one({"_id": doc["_id"]}, {"$set": {"status": "void"}})
        raise HTTPException(status_code=400, detail="This booking was cancelled or refunded, so the pass is void.")
    await db.passes.update_one({"_id": doc["_id"]}, {"$set": {
        "status": "redeemed", "redeemed_at": iso(now_utc()), "redeemed_by": user["id"],
        "redeemed_by_name": user.get("full_name", "")}})
    await notify(doc["user_id"], "Pass checked in",
                 f"Your pass for {doc['item_name']} was accepted by {user.get('full_name', 'the host')}. "
                 "Have a great time.", "order", "/orders", email=False)
    fresh = await db.passes.find_one({"_id": doc["_id"]})
    return {"ok": True, "pass": clean(fresh)}


@api.get("/partner/events/{event_id}/check-in")
async def event_check_in(event_id: str, user: dict = Depends(get_current_user)):
    """Live door list for the organiser of this event (or staff)."""
    ev = await db.events.find_one({"_id": as_oid(event_id, "event")})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found.")
    if ev.get("partner_id") != user["id"] and "events:view" not in perms_of(user):
        raise HTTPException(status_code=403, detail="That event isn't yours.")
    rows = await db.passes.find({"kind": "event", "ref_id": event_id}).limit(1000).to_list(1000)
    items = [clean(r) for r in rows]
    return {"event": {"id": event_id, "title": ev.get("title", ""), "starts_at": ev.get("starts_at", "")},
            "items": items, "guests": sum(int(r.get("quantity") or 1) for r in items),
            "arrived": sum(int(r.get("quantity") or 1) for r in items if r["status"] == "redeemed"),
            "valid": sum(1 for r in items if r["status"] == "valid")}


@api.get("/partner/events/{event_id}/check-in.csv")
async def event_check_in_csv(event_id: str, user: dict = Depends(get_current_user)):
    """Door list as a CSV the organiser can keep after the night."""
    data = await event_check_in(event_id, user)
    cols = ["code", "guest", "guests", "status", "arrived_at", "checked_in_by", "order_no"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for p in data["items"]:
        writer.writerow({"code": p["code"], "guest": p.get("user_name", ""),
                         "guests": p.get("quantity", 1), "status": p["status"],
                         "arrived_at": str(p.get("redeemed_at") or "")[:16].replace("T", " "),
                         "checked_in_by": p.get("redeemed_by_name", ""),
                         "order_no": p.get("order_no", "")})
    writer.writerow({})
    writer.writerow({"code": "TOTAL", "guest": data["event"]["title"],
                     "guests": data["guests"], "status": f"{data['arrived']} arrived"})
    name = "".join(ch if ch.isalnum() else "-" for ch in data["event"]["title"].lower())[:40]
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="door-{name}.csv"'})


async def door_sale_settlement(order: dict) -> dict | None:
    """The vendor already holds the cash, so Buddilio's commission is booked as owed BY the vendor."""
    try:
        import vendor_routes
        vendor_id = await vendor_routes.vendor_for_order(order)
        if not vendor_id:
            return None
        sched = await vendor_routes.active_schedule(vendor_id, order.get("ref_id", "")) or {}
    except Exception as exc:
        logger.warning(f"door settlement skipped for {order.get('order_no')}: {exc}")
        return None
    gross = float(order.get("charge_total") or order["total"])
    qty = max(int(order.get("quantity") or 1), 1)
    ctype = sched.get("commission_type", "percentage")
    cval = float(sched.get("commission_value") or 0)
    if ctype == "fixed":
        commission = cval * qty
    elif ctype == "percentage":
        commission = gross * cval / 100
    else:
        commission = gross * cval / 100 + float(sched.get("commission_fixed") or 0) * qty
    commission = round(min(max(commission, 0), gross), 2)
    row = {"vendor_id": vendor_id, "booking_id": str(order["_id"]), "order_no": order["order_no"],
           "gross": gross, "commission": commission, "platform_fee": 0.0, "refunds": 0.0,
           "adjustments": 0.0, "net": round(-commission, 2), "currency": order.get("currency", ""),
           "collected_by_vendor": True, "source": "door_sale",
           "note": f"Door sale collected by the organiser ({order.get('payment_method', 'cash')}). "
                   "Commission is recovered from the next payout.",
           "status": "pending", "due_on": iso(now_utc() + timedelta(days=7)),
           "created_at": iso(now_utc())}
    await db.vendor_settlements.insert_one(row)
    return row


class WalkInIn(BaseModel):
    guest_name: str
    guest_phone: str = ""
    guest_email: str = ""
    quantity: int = 1
    amount: float = 0.0
    method: str = "cash"          # cash | upi | card | paypal_link
    check_in_now: bool = True


@api.post("/partner/events/{event_id}/walk-in")
async def event_walk_in(event_id: str, payload: WalkInIn, user: dict = Depends(get_current_user)):
    """Door sale: the organiser collects the money in person, or sends a PayPal link on the spot."""
    ev = await db.events.find_one({"_id": as_oid(event_id, "event")})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found.")
    if ev.get("partner_id") != user["id"] and "events:view" not in perms_of(user):
        raise HTTPException(status_code=403, detail="That event isn't yours.")
    qty = max(int(payload.quantity or 1), 1)
    name = payload.guest_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Add the guest's name for the door list.")
    email = payload.guest_email.strip().lower()

    if payload.method == "paypal_link":
        if not email:
            raise HTTPException(status_code=400,
                                detail="A PayPal link needs the guest's email. Otherwise collect at the door.")
        guest = await db.users.find_one({"email": email})
        if not guest:
            raise HTTPException(status_code=400, detail=(
                "That email has no Buddilio account yet, so we can't send a pay link. Ask them to sign "
                "up, or take the money at the door and record it here."))
        amount = round(float(payload.amount or 0) or float(ev.get("price") or 0) * qty, 2)
        order = {"order_no": "BUD" + uuid.uuid4().hex[:8].upper(), "user_id": str(guest["_id"]),
                 "user_email": guest["email"], "user_name": guest.get("full_name", name),
                 "kind": "event", "ref_id": event_id, "item_name": ev["title"], "quantity": qty,
                 "subtotal": amount, "discount": 0.0, "tax": 0.0, "total": amount,
                 "tax_percent": 0.0, "tax_label": "No tax", "credit_applied": 0.0, "charge_credit": 0.0,
                 "coupon": "", "currency": BASE_CURRENCY, "fx_rate": 1.0, "base_currency": BASE_CURRENCY,
                 "charge_subtotal": amount, "charge_discount": 0.0, "charge_tax": 0.0,
                 "charge_total": amount, "payment_status": "pending", "order_status": "created",
                 "refund_status": "none", "gateway": "paypal", "transaction_id": "",
                 "walk_in": True, "walk_in_by": user["id"], "created_at": iso(now_utc())}
        oid_new = str((await db.orders.insert_one(order)).inserted_id)
        await notify(str(guest["_id"]), "Pay for your pass",
                     f"{ev['title']} — {fmt_money(amount)} is waiting to be paid. Open your orders and "
                     "tap Retry payment to pay with PayPal.", "order", "/orders")
        return {"mode": "paypal_link", "order_id": oid_new, "order_no": order["order_no"],
                "amount": amount, "pay_url": f"{FRONTEND_URL.rstrip('/')}/orders",
                "message": f"Pay link sent to {guest['email']}. The pass is issued the moment PayPal confirms."}

    if payload.method not in ("cash", "upi", "card"):
        raise HTTPException(status_code=400, detail="Choose cash, UPI, card machine or a PayPal link.")
    amount = round(float(payload.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Enter how much you collected.")
    guest = await db.users.find_one({"email": email}) if email else None
    cur = (ev.get("price_currency") or BASE_CURRENCY).upper()
    order = {"order_no": "BUD" + uuid.uuid4().hex[:8].upper(),
             "user_id": str(guest["_id"]) if guest else "", "user_email": email,
             "user_name": guest.get("full_name", name) if guest else name,
             "guest_name": name, "guest_phone": payload.guest_phone.strip(),
             "kind": "event", "ref_id": event_id, "item_name": ev["title"], "quantity": qty,
             "subtotal": amount, "discount": 0.0, "tax": 0.0, "total": amount,
             "tax_percent": 0.0, "tax_label": "Collected at the door",
             "credit_applied": 0.0, "charge_credit": 0.0, "coupon": "",
             "currency": cur, "fx_rate": 1.0, "base_currency": BASE_CURRENCY,
             "charge_subtotal": amount, "charge_discount": 0.0, "charge_tax": 0.0,
             "charge_total": amount, "payment_status": "paid", "order_status": "completed",
             "refund_status": "none", "gateway": "door", "payment_method": payload.method,
             "transaction_id": f"DOOR-{uuid.uuid4().hex[:6].upper()}",
             "walk_in": True, "walk_in_by": user["id"], "collected_by_vendor": True,
             "paid_at": iso(now_utc()), "created_at": iso(now_utc())}
    res = await db.orders.insert_one(order)
    order["_id"] = res.inserted_id
    await db.payments.insert_one({"order_id": str(res.inserted_id), "user_id": order["user_id"],
                                  "amount": amount, "status": "captured", "gateway": "door",
                                  "transaction_id": order["transaction_id"],
                                  "created_at": iso(now_utc())})
    await door_sale_settlement(order)          # commission owed on money the vendor already holds
    voucher = await issue_pass(order)
    if payload.check_in_now and voucher:
        await db.passes.update_one({"code": voucher["code"]}, {"$set": {
            "status": "redeemed", "redeemed_at": iso(now_utc()), "redeemed_by": user["id"],
            "redeemed_by_name": user.get("full_name", "")}})
        voucher = clean(await db.passes.find_one({"code": voucher["code"]}))
    if guest:
        await db.event_participants.update_one(
            {"event_id": event_id, "user_id": str(guest["_id"])},
            {"$setOnInsert": {"event_id": event_id, "user_id": str(guest["_id"]),
                              "status": "confirmed", "order_id": str(res.inserted_id),
                              "created_at": iso(now_utc())}}, upsert=True)
    await db.events.update_one({"_id": ev["_id"]}, {"$inc": {"participant_count": qty}})
    logger.info(f"door sale {order['order_no']} · {ev['title']} · {payload.method} · {amount}")
    return {"mode": "collected", "order_no": order["order_no"], "amount": amount,
            "method": payload.method, "pass": voucher,
            "message": f"{name} is in. {fmt_money(amount, cur)} recorded as collected by you — "
                       "Buddilio's commission comes off your next settlement."}


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


class CredentialIn(BaseModel):
    value: str = Field(min_length=1, max_length=4000)


def strong_password(p: str) -> str:
    p = (p or "").strip()
    if len(p) < 10 or len(p) > 128:
        raise HTTPException(status_code=400, detail="Use between 10 and 128 characters.")
    if not (any(c.isupper() for c in p) and any(c.islower() for c in p) and any(c.isdigit() for c in p)):
        raise HTTPException(status_code=400,
                            detail="Include an upper-case letter, a lower-case letter and a number.")
    return p


def keyholder(user: dict) -> dict:
    """Super admin, or an admin you granted the credentials permission."""
    if user.get("staff_role") == "super_admin" or "credentials:manage" in perms_of(user):
        return user
    raise HTTPException(status_code=403, detail="Only a Super admin can manage credentials.")


async def end_sessions(user_id: str) -> int:
    """Bumping the token version invalidates every token already issued to this account."""
    await db.users.update_one({"_id": as_oid(user_id, "user")}, {"$inc": {"token_version": 1}})
    doc = await db.users.find_one({"_id": as_oid(user_id, "user")}, {"token_version": 1})
    return int(doc.get("token_version") or 0)


@api.post("/me/password")
async def change_my_password(payload: PasswordChangeIn, response: Response,
                            user: dict = Depends(get_current_user)):
    row = await db.users.find_one({"_id": as_oid(user["id"], "user")})
    if not verify_password(payload.current_password, row.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="That current password is not right.")
    new = strong_password(payload.new_password)
    if verify_password(new, row.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Please choose a different password.")
    await db.users.update_one({"_id": row["_id"]}, {"$set": {"password_hash": hash_password(new),
                                                            "password_changed_at": iso(now_utc())}})
    version = await end_sessions(user["id"])
    await audit(user, "password.changed", "user", user["id"], {})
    token = create_access_token(user["id"], row["email"], row.get("role", "user"), version)
    set_cookies(response, token)
    return {"ok": True, "access_token": token,
            "message": "Password changed. Every other device has been signed out."}


@api.get("/admin/security/accounts")
async def security_accounts(user: dict = Depends(get_current_user)):
    keyholder(user)
    rows = await db.users.find({"role": {"$in": ["admin", "manager", "partner"]}},
                               {"full_name": 1, "email": 1, "role": 1, "staff_role": 1, "status": 1,
                                "password_changed_at": 1, "last_login_at": 1, "created_at": 1}) \
        .sort("role", 1).limit(200).to_list(200)
    return {"items": [clean(r) for r in rows], "me": user["id"]}


@api.post("/admin/security/accounts/{uid}/password")
async def admin_reset_password(uid: str, payload: CredentialIn, user: dict = Depends(get_current_user)):
    keyholder(user)
    if uid == user["id"]:
        raise HTTPException(status_code=400, detail="Change your own password from 'My password'.")
    row = await db.users.find_one({"_id": as_oid(uid, "user")})
    if not row:
        raise HTTPException(status_code=404, detail="Account not found.")
    new = strong_password(payload.value)
    await db.users.update_one({"_id": row["_id"]}, {"$set": {"password_hash": hash_password(new),
                                                            "password_changed_at": iso(now_utc())}})
    await end_sessions(uid)
    await audit(user, "password.admin_reset", "user", uid, {"email": row.get("email", "")})
    await notify(uid, "Your password was changed",
                 "A Buddilio administrator set a new password for your account. If this wasn't "
                 "expected, contact the Super admin.", "system", "/login")
    return {"ok": True, "message": f"New password set for {row.get('email', 'that account')}. "
                                   "They have been signed out everywhere."}


@api.post("/admin/security/accounts/{uid}/revoke")
async def admin_revoke_sessions(uid: str, user: dict = Depends(get_current_user)):
    keyholder(user)
    row = await db.users.find_one({"_id": as_oid(uid, "user")}, {"email": 1})
    if not row:
        raise HTTPException(status_code=404, detail="Account not found.")
    await end_sessions(uid)
    await audit(user, "sessions.revoked", "user", uid, {"email": row.get("email", "")})
    return {"ok": True, "message": "Signed out of every device."}


@api.post("/admin/security/accounts/{uid}/access")
async def admin_set_access(uid: str, body: dict = Body(default={}),
                           user: dict = Depends(get_current_user)):
    keyholder(user)
    if uid == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot lock your own account.")
    row = await db.users.find_one({"_id": as_oid(uid, "user")}, {"email": 1, "status": 1})
    if not row:
        raise HTTPException(status_code=404, detail="Account not found.")
    active = bool(body.get("active", False))
    await db.users.update_one({"_id": row["_id"]},
                              {"$set": {"status": "active" if active else "suspended"}})
    await end_sessions(uid)
    await audit(user, "access.restored" if active else "access.revoked", "user", uid,
                {"email": row.get("email", "")})
    return {"ok": True, "status": "active" if active else "suspended",
            "message": ("Access restored." if active else
                        "Access revoked and all their sessions killed.")}


@api.get("/admin/credentials")
async def list_credentials(user: dict = Depends(get_current_user)):
    keyholder(user)
    rows = await db.audit_logs.find({"action": {"$regex": "^(credential|password|access|sessions)\\."}}) \
        .sort("created_at", -1).limit(40).to_list(40)
    return {"items": await vault.status(db), "history": [clean(r) for r in rows],
            "not_managed_here": [
                {"what": "Hostinger account password", "where": "hpanel.hostinger.com → Account → Security"},
                {"what": "Database (MongoDB) password", "where": "Your MongoDB Atlas project → Database Access"},
                {"what": "Domain / DNS login", "where": "Wherever buddilio.com is registered"},
                {"what": "PayPal business account login", "where": "paypal.com → Security"}]}


@api.put("/admin/credentials/{name}")
async def set_credential(name: str, payload: CredentialIn, user: dict = Depends(get_current_user)):
    keyholder(user)
    if name not in vault.NAMES:
        raise HTTPException(status_code=404, detail="That setting isn't managed here.")
    value = payload.value.strip()
    if name == "PAYPAL_ENV" and value.lower() not in ("live", "sandbox"):
        raise HTTPException(status_code=400, detail="PayPal mode must be live or sandbox.")
    if name == "JWT_SECRET" and len(value) < 24:
        raise HTTPException(status_code=400, detail="Use at least 24 characters for the login secret.")
    await vault.set_secret(db, name, value)
    await audit(user, "credential.updated", "credential", name, {"name": name})
    logger.info(f"credential {name} updated by {user['email']}")
    extra = (" Everyone will need to log in again." if name == "JWT_SECRET" else "")
    return {"ok": True, "message": f"Saved. Buddilio is now using the new {name}.{extra}"}


@api.delete("/admin/credentials/{name}")
async def reset_credential(name: str, user: dict = Depends(get_current_user)):
    keyholder(user)
    if name not in vault.NAMES:
        raise HTTPException(status_code=404, detail="That setting isn't managed here.")
    await vault.clear_secret(db, name)
    await audit(user, "credential.reverted", "credential", name, {"name": name})
    return {"ok": True, "message": "Reverted to the value in the server file."}


@api.post("/admin/credentials/test/{service}")
async def test_credential(service: str, user: dict = Depends(get_current_user)):
    keyholder(user)
    if service == "paypal":
        if not paypal.enabled():
            return {"ok": False, "message": "PayPal keys are not set."}
        try:
            await paypal.list_webhooks()
        except paypal.PayPalError as exc:
            return {"ok": False, "message": paypal.message_of(exc)}
        return {"ok": True, "message": f"PayPal answered in {os.environ.get('PAYPAL_ENV', 'sandbox')} mode."}
    if service == "email":
        if not os.environ.get("RESEND_API_KEY"):
            return {"ok": False, "message": "No email key is set."}
        sent = await send_email(user["email"], "Buddilio credential test",
                               "<p>Your Resend key works — this email came from Buddilio.</p>")
        return {"ok": bool(sent), "message": ("Test email sent to " + user["email"]) if sent
                else "Resend rejected the request. Check the key."}
    if service == "ai":
        if not ai.ai_enabled():
            return {"ok": False, "message": "No AI key is set."}
        try:
            reply = await ai.draft_event_copy(f"cred-test-{uuid.uuid4().hex[:6]}",
                                              "Rooftop jazz night for 40 guests in Dubai")
            return {"ok": bool(reply), "message": "AI key works — Buddy answered."
                    if reply else "AI key was accepted but returned nothing usable."}
        except Exception as exc:
            return {"ok": False, "message": f"AI key failed: {str(exc)[:120]}"}
    raise HTTPException(status_code=404, detail="Nothing to test for that service.")


CANCEL_TIERS = [(7, 30), (2, 50), (0, 100)]   # days notice -> % deducted (minimum 30%)


async def cancellation_deduction(order: dict) -> tuple[float, int, str]:
    """Returns (refundable amount, deduction %, reason) using the published tiers."""
    if order["kind"] == "membership":
        return 0.0, 100, "Membership fees are non-refundable."
    paid = float(order.get("charge_total") or order["total"])
    start = ""
    if order["kind"] == "event" and ObjectId.is_valid(order.get("ref_id", "")):
        ev = await db.events.find_one({"_id": ObjectId(order["ref_id"])}, {"starts_at": 1})
        start = (ev or {}).get("starts_at", "")
    days = 999
    if start:
        try:
            days = (datetime.fromisoformat(str(start).replace("Z", "+00:00")) - now_utc()).days
        except ValueError:
            days = 999
    pct = next((p for d, p in CANCEL_TIERS if days >= d), 100)
    label = ("more than 7 days" if days >= 7 else "2-7 days" if days >= 2 else "under 48 hours")
    return round(paid * (100 - pct) / 100, 2), pct, f"Cancelled {label} before the booking."


@api.get("/me/orders/{oid}/cancellation-quote")
async def cancellation_quote(oid: str, user: dict = Depends(get_current_user)):
    order = await db.orders.find_one({"_id": as_oid(oid, "order"), "user_id": user["id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    refundable, pct, reason = await cancellation_deduction(order)
    return {"paid": float(order.get("charge_total") or order["total"]), "currency": order.get("currency"),
            "deduction_percent": pct, "refundable": refundable, "reason": reason,
            "credit_option": round(refundable * 1.1, 2) if refundable > 0 else 0.0,
            "cancellable": order["payment_status"] == "paid" and order.get("refund_status", "none") == "none"}


class CancelIn(BaseModel):
    reason: str = ""
    prefer: str = "refund"   # refund | credit


@api.post("/me/orders/{oid}/cancel")
async def cancel_my_order(oid: str, payload: CancelIn = Body(default=CancelIn()),
                          user: dict = Depends(get_current_user)):
    """Member-initiated cancellation. Entitlement stops now; the money decision sits with admin."""
    order = await db.orders.find_one({"_id": as_oid(oid, "order"), "user_id": user["id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    if order["payment_status"] != "paid":
        raise HTTPException(status_code=400, detail="Only a paid booking can be cancelled.")
    if order.get("cancellation", {}).get("status") in ("requested", "settled"):
        raise HTTPException(status_code=400, detail="This booking is already cancelled.")
    refundable, pct, reason = await cancellation_deduction(order)
    cancellation = {"status": "requested", "requested_at": iso(now_utc()), "reason": payload.reason,
                    "deduction_percent": pct, "refundable": refundable,
                    "prefer": "credit" if payload.prefer == "credit" else "refund",
                    "policy_note": reason}
    await db.orders.update_one({"_id": order["_id"]}, {"$set": {
        "order_status": "cancelled", "cancellation": cancellation}})
    await db.passes.update_many({"order_id": oid}, {"$set": {"status": "void"}})
    if order["kind"] == "event":
        part = await db.event_participants.find_one({"order_id": oid})
        if part:
            await db.event_participants.delete_one({"_id": part["_id"]})
            count = await db.event_participants.count_documents({"event_id": order["ref_id"],
                                                                 "status": "confirmed"})
            await db.events.update_one({"_id": ObjectId(order["ref_id"])},
                                       {"$set": {"participant_count": count}})
            await promote_waitlist(order["ref_id"])
    if order["kind"] == "membership":
        await db.user_memberships.update_many({"order_id": oid}, {"$set": {"status": "cancelled",
                                                                          "auto_renews": False}})
    for admin in await db.users.find({"role": "admin"}, {"_id": 1}).limit(20).to_list(20):
        await notify(str(admin["_id"]), "Cancellation to settle",
                     f"#{order['order_no']} cancelled by the member. {pct}% deduction applies — "
                     f"{fmt_money(refundable, order.get('currency'))} refundable.", "order", "/admin")
    await notify(user["id"], "Booking cancelled",
                 f"{order['item_name']} is cancelled. {pct}% is deducted as per the cancellation policy, "
                 f"so {fmt_money(refundable, order.get('currency'))} is due back once Buddilio settles it.",
                 "order", "/orders")
    return {"cancellation": cancellation}


@api.get("/admin/cancellations")
async def admin_cancellations(user: dict = Depends(require_perm("finance:manage"))):
    rows = await db.orders.find({"cancellation.status": "requested"}).sort("cancellation.requested_at", -1) \
        .limit(200).to_list(200)
    return {"items": [clean(r) for r in rows], "tiers": CANCEL_TIERS}


class SettleIn(BaseModel):
    amount: float = -1.0
    as_credit: bool = False
    note: str = ""


@api.post("/admin/orders/{oid}/settle-cancellation")
async def settle_cancellation(oid: str, payload: SettleIn = Body(default=SettleIn()),
                              user: dict = Depends(require_perm("finance:manage"))):
    """Admin decides the final amount — as a gateway refund or as Buddilio credit."""
    order = await db.orders.find_one({"_id": as_oid(oid, "order")})
    if not order or (order.get("cancellation") or {}).get("status") != "requested":
        raise HTTPException(status_code=400, detail="This order has no cancellation awaiting settlement.")
    quoted = float(order["cancellation"]["refundable"])
    amount = round(quoted if payload.amount < 0 else float(payload.amount), 2)
    paid = float(order.get("charge_total") or order["total"])
    if amount < 0 or amount - paid > 0.005:
        raise HTTPException(status_code=400, detail=f"Enter an amount between 0 and {paid:.2f}.")
    settled = {**order["cancellation"], "status": "settled", "settled_at": iso(now_utc()),
               "settled_by": user["id"], "settled_amount": amount,
               "method": "credit" if payload.as_credit else "refund", "note": payload.note}
    if amount > 0 and payload.as_credit:
        await grant_credit(order["user_id"], amount,
                           f"Cancellation credit for #{order['order_no']}")
        await db.orders.update_one({"_id": order["_id"]},
                                   {"$set": {"cancellation": settled, "refund_status": "credited",
                                             "refunded_amount": amount}})
    elif amount > 0:
        await refund_order(oid, RefundIn(amount=amount, override_policy=amount > quoted + 0.005,
                                         reason=payload.note or "Cancellation settlement"), user)
        await db.orders.update_one({"_id": order["_id"]}, {"$set": {"cancellation": settled}})
    else:
        await db.orders.update_one({"_id": order["_id"]}, {"$set": {"cancellation": settled}})
        await notify(order["user_id"], "Cancellation settled",
                     f"#{order['order_no']} is closed with no refund as per the cancellation policy.",
                     "order", "/orders")
    await audit(user, "order.cancellation_settled", "order", oid,
                {"amount": amount, "as_credit": payload.as_credit, "quoted": quoted})
    return {"cancellation": settled}


async def promote_waitlist(event_id: str) -> int:
    """Tells the next people on an event waitlist that a seat opened up."""
    ev = await db.events.find_one({"_id": ObjectId(event_id)}, {"title": 1, "capacity": 1,
                                                                "participant_count": 1})
    if not ev:
        return 0
    free = int(ev.get("capacity") or 0) - int(ev.get("participant_count") or 0)
    if free <= 0:
        return 0
    rows = await db.event_waitlist.find({"event_id": event_id, "status": "waiting"}) \
        .sort("created_at", 1).limit(free).to_list(free)
    for row in rows:
        await db.event_waitlist.update_one({"_id": row["_id"]}, {"$set": {
            "status": "offered", "offered_at": iso(now_utc())}})
        await notify(row["user_id"], f"A seat opened up — {ev.get('title', 'an event')}",
                     "Someone cancelled, so there's room again. Book now before it's taken.",
                     "event", f"/events/{event_id}")
    return len(rows)


@api.post("/events/{event_id}/waitlist")
async def join_event_waitlist(event_id: str, user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"_id": as_oid(event_id, "event")}, {"title": 1})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found.")
    await db.event_waitlist.update_one({"event_id": event_id, "user_id": user["id"]},
                                       {"$setOnInsert": {"event_id": event_id, "user_id": user["id"],
                                                          "status": "waiting",
                                                          "created_at": iso(now_utc())}}, upsert=True)
    count = await db.event_waitlist.count_documents({"event_id": event_id, "status": "waiting"})
    return {"ok": True, "waiting": count,
            "message": "You're on the waitlist — we'll email you the moment a seat frees up."}


@api.get("/me/orders")
async def my_orders(user: dict = Depends(get_current_user)):
    docs = await db.orders.find({"user_id": user["id"]}).sort([("created_at", -1)]).limit(200).to_list(200)
    return {"items": [clean(d) for d in docs]}


# ---------------- referrals / credit / push ----------------
@api.get("/me/referrals")
async def my_referrals(user: dict = Depends(get_current_user)):
    doc = await db.users.find_one({"_id": ObjectId(user["id"])})
    code = await ensure_ref_code(doc)
    invites = [{"name": r.get("invitee_name", ""), "status": r["status"],
                "created_at": r["created_at"], "rewarded_at": r.get("rewarded_at", "")}
               for r in await db.referrals.find({"referrer_id": user["id"]}).sort([("created_at", -1)]).limit(200).to_list(200)]
    credits = [clean(c) for c in await db.credits.find({"user_id": user["id"]}).sort([("created_at", -1)]).limit(100).to_list(100)]
    rewarded = sum(1 for i in invites if i["status"] == "rewarded")
    return {"code": code, "link": f"{FRONTEND_URL}/register?ref={code}", "reward": REFERRAL_REWARD,
            "balance": await credit_balance(user["id"]), "invites": invites, "credits": credits,
            "joined": len(invites), "rewarded": rewarded, "badge": badge_for(rewarded)}


@api.get("/referrals/leaderboard")
async def referral_leaderboard(month: str = "", user: Optional[dict] = Depends(optional_user)):
    month = (month or now_utc().strftime("%Y-%m"))[:7]
    docs = await db.referrals.find({"status": "rewarded",
                                    "rewarded_at": {"$regex": f"^{month}"}},
                                   {"referrer_id": 1}).limit(5000).to_list(5000)
    tally: dict[str, int] = {}
    for d in docs:
        tally[d["referrer_id"]] = tally.get(d["referrer_id"], 0) + 1
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    top = ranked[:10]
    people = await load_many(db.users, [uid for uid, _ in top],
                             {"full_name": 1, "photo": 1, "city": 1})
    lifetimes: dict[str, int] = {}
    for d in await db.referrals.aggregate([
            {"$match": {"status": "rewarded"}},
            {"$group": {"_id": "$referrer_id", "n": {"$sum": 1}}}]).to_list(5000):
        lifetimes[d["_id"]] = d["n"]
    rows = []
    for i, (uid, count) in enumerate(top):
        u = people.get(uid)
        rows.append({"rank": i + 1, "name": short_name((u or {}).get("full_name", "")),
                     "photo": (u or {}).get("photo", ""), "city": (u or {}).get("city", ""),
                     "invites": count, "credit": round(count * REFERRAL_REWARD, 2),
                     "badge": badge_for(lifetimes.get(uid, 0))["name"],
                     "me": bool(user) and uid == user["id"]})
    me = None
    if user:
        mine = tally.get(user["id"], 0)
        lifetime = lifetimes.get(user["id"], 0)
        me = {"rank": next((i + 1 for i, (uid, _) in enumerate(ranked) if uid == user["id"]), 0),
              "invites": mine, "lifetime": lifetime,
              "credit": round(mine * REFERRAL_REWARD, 2), "badge": badge_for(lifetime)}
    champ = await db.prizes.find_one({"month": last_month()})
    return {"month": month, "items": rows, "reward": REFERRAL_REWARD, "prize": PRIZE_LABEL, "me": me,
            "champion": {"month": champ["month"], "month_label": month_label(champ["month"]),
                         "name": champ["name"], "city": champ.get("city", ""),
                         "photo": champ.get("photo", ""), "invites": champ["invites"],
                         "prize": champ.get("prize", PRIZE_LABEL),
                         "me": bool(user) and champ["user_id"] == user["id"]} if champ else None,
            "participants": len(ranked)}


@api.get("/referrals/{code}")
async def referral_lookup(code: str):
    u = await db.users.find_one({"referral_code": code.strip().upper()}, {"full_name": 1})
    if not u:
        raise HTTPException(status_code=404, detail="That invite link is not valid any more.")
    return {"referrer_name": u["full_name"].split(" ")[0], "reward": REFERRAL_REWARD}


@api.get("/push/config")
async def push_config():
    return {"enabled": push_enabled(), "public_key": vapid_public_key()}


@api.post("/push/subscribe")
async def push_subscribe(payload: PushSubIn, user: dict = Depends(get_current_user)):
    if not payload.keys.get("p256dh") or not payload.keys.get("auth"):
        raise HTTPException(status_code=400, detail="This device sent an invalid push subscription.")
    await db.push_subscriptions.update_one(
        {"endpoint": payload.endpoint},
        {"$set": {"user_id": user["id"], "endpoint": payload.endpoint, "keys": payload.keys,
                  "updated_at": iso(now_utc())},
         "$setOnInsert": {"created_at": iso(now_utc())}}, upsert=True)
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"notification_prefs.push": True}})
    return {"ok": True}


@api.post("/push/unsubscribe")
async def push_unsubscribe(body: dict, user: dict = Depends(get_current_user)):
    await db.push_subscriptions.delete_many({"user_id": user["id"],
                                             "endpoint": body.get("endpoint", "")})
    if not await db.push_subscriptions.find_one({"user_id": user["id"]}):
        await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"notification_prefs.push": False}})
    return {"ok": True}


@api.post("/push/test")
async def push_test(user: dict = Depends(get_current_user)):
    sent = await push_to(db, user["id"], {
        "title": "Buddilio alerts are on",
        "body": "This is how a new message or an event reminder will reach you.",
        "url": "/dashboard", "tag": "test"})
    if not sent:
        raise HTTPException(status_code=400, detail="No active device found. Turn alerts on for this device first.")
    return {"sent": sent}


# ---------------- messaging ----------------
@api.post("/conversations")
async def start_conversation(body: dict, user: dict = Depends(get_current_user)):
    other_id = body.get("user_id")
    other = await db.users.find_one({"_id": ObjectId(other_id)})
    if not other:
        raise HTTPException(status_code=404, detail="User not found")
    if user["id"] in other.get("blocked", []):
        raise HTTPException(status_code=403, detail="You cannot message this member.")
    conv = await db.conversations.find_one({"type": "direct", "members": {"$all": [user["id"], other_id]}})
    if not conv:
        res = await db.conversations.insert_one({
            "type": "direct", "members": [user["id"], other_id], "event_id": "",
            "title": "", "last_message": "", "updated_at": iso(now_utc()),
            "created_at": iso(now_utc())})
        conv = await db.conversations.find_one({"_id": res.inserted_id})
    return clean(conv)


@api.get("/conversations")
async def list_conversations(user: dict = Depends(get_current_user)):
    docs = await db.conversations.find({"members": user["id"]}).sort([("updated_at", -1)]).limit(100).to_list(100)
    others = [next((m for m in d.get("members", []) if m != user["id"]), None)
              for d in docs if d.get("type") == "direct"]
    people = await load_many(db.users, [o for o in others if o], {"full_name": 1, "photo": 1})
    unread: dict[str, int] = {}
    for row in await db.messages.aggregate([
            {"$match": {"conversation_id": {"$in": [str(d["_id"]) for d in docs]},
                        "sender_id": {"$ne": user["id"]}, "read": False}},
            {"$group": {"_id": "$conversation_id", "n": {"$sum": 1}}}]).to_list(200):
        unread[row["_id"]] = row["n"]
    out = []
    for d in docs:
        c = clean(d)
        if c["type"] == "direct":
            oid = next((m for m in c["members"] if m != user["id"]), None)
            other = people.get(oid) if oid else None
            c["title"] = other["full_name"] if other else "Buddilio member"
            c["avatar"] = other.get("photo", "") if other else ""
            c["other_id"] = oid
        c["unread"] = unread.get(c["id"], 0)
        c["online"] = bool(hub.online_among([m for m in c["members"] if m != user["id"]])) if c["type"] == "direct" else False
        out.append(c)
    return {"items": out}


@api.get("/conversations/{cid}/messages")
async def get_messages(cid: str, user: dict = Depends(get_current_user)):
    conv = await db.conversations.find_one({"_id": ObjectId(cid)})
    if not conv or user["id"] not in conv["members"]:
        raise HTTPException(status_code=403, detail="You are not part of this conversation.")
    await db.messages.update_many({"conversation_id": cid, "sender_id": {"$ne": user["id"]}},
                                  {"$set": {"read": True}})
    docs = await db.messages.find({"conversation_id": cid}).sort([("created_at", 1)]).limit(500).to_list(500)
    senders = await load_many(db.users, [d["sender_id"] for d in docs], {"full_name": 1, "photo": 1})
    out = []
    for d in docs:
        m = clean(d)
        u = senders.get(m["sender_id"])
        m["sender_name"] = u["full_name"] if u else "Member"
        m["sender_photo"] = u.get("photo", "") if u else ""
        out.append(m)
    await hub.send_to([m for m in conv["members"] if m != user["id"]],
                      {"type": "read", "conversation_id": cid, "by": user["id"]})
    return {"items": out}


async def ensure_event_chat(event_id: str, user_id: str) -> Optional[str]:
    """Event group chat is limited to paid ticket holders plus the organiser."""
    ev = await db.events.find_one({"_id": ObjectId(event_id)})
    if not ev:
        return None
    conv = await db.conversations.find_one({"type": "event", "event_id": event_id})
    if not conv:
        res = await db.conversations.insert_one({
            "type": "event", "event_id": event_id, "members": [ev["partner_id"]] if ev.get("partner_id") else [],
            "title": ev["title"], "last_message": "", "updated_at": iso(now_utc()),
            "created_at": iso(now_utc())})
        conv = await db.conversations.find_one({"_id": res.inserted_id})
    if user_id not in conv["members"]:
        await db.conversations.update_one({"_id": conv["_id"]}, {"$addToSet": {"members": user_id}})
    return str(conv["_id"])


@api.get("/events/{event_id}/chat")
async def event_chat(event_id: str, user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"_id": ObjectId(event_id)})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    is_organiser = ev.get("partner_id") == user["id"] or user["role"] == "admin"
    part = await db.event_participants.find_one({"event_id": event_id, "user_id": user["id"], "status": "confirmed"})
    paid = False
    if part and part.get("order_id"):
        order = await db.orders.find_one({"_id": ObjectId(part["order_id"]), "payment_status": "paid"})
        paid = bool(order)
    if not (is_organiser or paid):
        raise HTTPException(status_code=403, detail="The group chat opens once your paid ticket is confirmed.")
    cid = await ensure_event_chat(event_id, user["id"])
    return {"conversation_id": cid}


@api.post("/conversations/{cid}/messages")
async def send_message(cid: str, payload: MessageIn, user: dict = Depends(get_current_user)):
    conv = await db.conversations.find_one({"_id": ObjectId(cid)})
    if not conv or user["id"] not in conv["members"]:
        raise HTTPException(status_code=403, detail="You are not part of this conversation.")
    if not payload.body.strip() and not payload.attachment_path:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    limits = await plan_limits(user["id"])
    left = await messages_left(user["id"], limits)
    if left is not None and left <= 0:
        raise HTTPException(status_code=403,
                            detail=f"Your {limits['plan_name']} plan includes "
                                   f"{limits['messages_per_week']} messages a week. Upgrade for unlimited chat.")
    attachment = None
    if payload.attachment_path:
        rec = await db.files.find_one({"storage_path": payload.attachment_path,
                                       "owner_id": user["id"], "is_deleted": False})
        if not rec:
            raise HTTPException(status_code=400, detail="That attachment is no longer available.")
        attachment = {"url": f"/api/files/{rec['storage_path']}", "path": rec["storage_path"],
                      "name": rec.get("original_filename", "file"),
                      "content_type": rec.get("content_type", ""), "size": rec.get("size", 0)}
    doc = {"conversation_id": cid, "sender_id": user["id"], "body": payload.body.strip()[:2000],
           "attachment": attachment, "read": False, "created_at": iso(now_utc())}
    res = await db.messages.insert_one(doc)
    preview = doc["body"][:80] or ("Sent a photo" if (attachment or {}).get("content_type", "").startswith("image/")
                                   else "Sent a file")
    await db.conversations.update_one({"_id": conv["_id"]},
                                      {"$set": {"last_message": preview, "updated_at": iso(now_utc())}})
    for m in conv["members"]:
        if m != user["id"]:
            await notify(m, "New message", f"{user['full_name']}: {preview[:60]}", "message", "/messages", email=False)
    out = clean(await db.messages.find_one({"_id": res.inserted_id}))
    out["sender_name"] = user["full_name"]
    out["sender_photo"] = user.get("photo", "")
    await hub.send_to(conv["members"], {"type": "message", "conversation_id": cid, "message": out})
    return out


@api.delete("/conversations/{cid}")
async def delete_conversation(cid: str, user: dict = Depends(get_current_user)):
    conv = await db.conversations.find_one({"_id": ObjectId(cid)})
    if not conv or user["id"] not in conv["members"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.conversations.update_one({"_id": conv["_id"]}, {"$pull": {"members": user["id"]}})
    return {"ok": True}


# ---------------- notifications ----------------
@api.get("/notifications")
async def notifications(user: dict = Depends(get_current_user)):
    docs = await db.notifications.find({"user_id": user["id"]}).sort([("created_at", -1)]).limit(100).to_list(100)
    unread = await db.notifications.count_documents({"user_id": user["id"], "read": False})
    return {"items": [clean(d) for d in docs], "unread": unread}


@api.post("/notifications/read-all")
async def read_all(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


# ---------------- dashboard / search / cms ----------------
@api.get("/me/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    membership = await membership_active(user["id"])
    u = await db.users.find_one({"_id": ObjectId(user["id"])})
    filled = sum(1 for f in ["photo", "bio", "city", "mobile"] if u.get(f))
    filled += 1 if u.get("interests") else 0
    filled += 1 if u.get("event_categories") else 0
    rec_events = await db.events.find(
        {"status": "published", "starts_at": {"$gte": iso(now_utc())},
         "$or": [{"city": u.get("city")}, {"category": {"$in": u.get("event_categories", [])}}]}
    ).limit(6).to_list(6)
    if not rec_events:
        rec_events = await db.events.find({"status": "published"}).limit(6).to_list(6)
    rec_people = await db.users.find(
        {"role": "user", "status": "active", "_id": {"$ne": u["_id"]},
         "$or": [{"city": u.get("city")}, {"interests": {"$in": u.get("interests", [])}}]},
        PUBLIC_FIELDS).limit(6).to_list(6)
    return {
        "profile_completion": round(filled / 6 * 100),
        "membership": membership,
        "unread_messages": await db.messages.count_documents(
            {"sender_id": {"$ne": user["id"]}, "read": False,
             "conversation_id": {"$in": [str(c["_id"]) for c in await db.conversations.find({"members": user["id"]}).limit(100).to_list(100)]}}),
        "unread_notifications": await db.notifications.count_documents({"user_id": user["id"], "read": False}),
        "orders": await db.orders.count_documents({"user_id": user["id"]}),
        "upcoming_events": [clean(e) for e in await db.events.find(
            {"_id": {"$in": [ObjectId(p["event_id"]) for p in await db.event_participants.find({"user_id": user["id"]}).limit(50).to_list(50)]}}
        ).limit(5).to_list(5)],
        "recommended_events": [clean(e) for e in rec_events],
        "recommended_people": [clean(p) for p in rec_people],
        "saved_count": len(u.get("saved_events", [])),
    }


@api.get("/search")
async def global_search(q: str):
    if not q:
        return {"users": [], "events": [], "products": []}
    rx = {"$regex": q, "$options": "i"}
    users = await db.users.find({"full_name": rx, "role": "user", "status": "active"}, PUBLIC_FIELDS).limit(5).to_list(5)
    events = await db.events.find({"title": rx, "status": "published"}).limit(5).to_list(5)
    prods = await db.products.find({"name": rx, "active": True}).limit(5).to_list(5)
    return {"users": [clean(u) for u in users], "events": [clean(e) for e in events],
            "products": [clean(p) for p in prods]}


CRON_SECRET = os.environ.get("WEBHOOK_CRON_SECRET", "")
PRIZE_LABEL = "a free Buddilio pass"


def cron_guard(authorization: str = Header("")):
    token = authorization[7:] if authorization[:7].lower() == "bearer " else ""
    if not CRON_SECRET or not secrets.compare_digest(token, CRON_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def month_tally(month: str) -> list:
    docs = await db.referrals.find({"status": "rewarded", "rewarded_at": {"$regex": f"^{month}"}},
                                   {"referrer_id": 1}).limit(5000).to_list(5000)
    tally: dict[str, int] = {}
    for d in docs:
        tally[d["referrer_id"]] = tally.get(d["referrer_id"], 0) + 1
    return sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))


def last_month() -> str:
    return (now_utc().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def month_label(month: str) -> str:
    try:
        return datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    except Exception:
        return month


async def award_monthly_prize(month: str = "") -> dict:
    """The month's top inviter wins a free pass. Idempotent — one prize per month."""
    month = month or last_month()
    existing = await db.prizes.find_one({"month": month})
    if existing:
        return {"month": month, "status": "already_awarded", "winner": existing.get("name", "")}
    ranked = await month_tally(month)
    if not ranked:
        return {"month": month, "status": "no_participants"}
    uid, invites = ranked[0]
    try:
        winner = await db.users.find_one({"_id": ObjectId(uid)})
    except Exception:
        winner = None
    if not winner:
        return {"month": month, "status": "winner_missing"}

    prod = await db.products.find_one({"active": True, "city": winner.get("city", "")},
                                      sort=[("price", -1)]) \
        or await db.products.find_one({"active": True}, sort=[("price", -1)])
    order_id, item = "", PRIZE_LABEL
    if prod:
        item = prod["name"]
        order = {
            "order_no": "BUD" + uuid.uuid4().hex[:8].upper(), "user_id": uid,
            "user_email": winner.get("email", ""), "kind": "product", "ref_id": str(prod["_id"]),
            "item_name": item, "quantity": 1,
            "subtotal": prod["price"], "discount": prod["price"], "tax": 0.0, "total": 0.0,
            "tax_percent": 0.0, "tax_label": "Tax", "credit_applied": 0.0, "charge_credit": 0.0,
            "coupon": "LEADERBOARD", "currency": BASE_CURRENCY, "fx_rate": 1.0,
            "base_currency": BASE_CURRENCY, "charge_subtotal": prod["price"],
            "charge_discount": prod["price"], "charge_tax": 0.0, "charge_total": 0.0,
            "payment_status": "paid", "order_status": "completed", "refund_status": "none",
            "gateway": "leaderboard_prize", "transaction_id": f"PRIZE-{month}",
            "prize_month": month, "created_at": iso(now_utc()), "paid_at": iso(now_utc()),
        }
        order_id = str((await db.orders.insert_one(order)).inserted_id)

    name = short_name(winner.get("full_name", ""))
    await db.prizes.insert_one({
        "month": month, "user_id": uid, "name": name, "city": winner.get("city", ""),
        "photo": winner.get("photo", ""), "invites": invites, "prize": item,
        "order_id": order_id, "created_at": iso(now_utc())})

    await notify(uid, f"You won {month_label(month)} on the leaderboard",
                 f"You brought {invites} friend{'' if invites == 1 else 's'} to Buddilio last month — "
                 f"the most of anyone. {item} is now in your orders, on us.",
                 "order", "/orders")
    for other_id, count in ranked[1:20]:
        await notify(other_id, f"{name} won {month_label(month)}",
                     f"{name} topped the invite leaderboard with {invites} friends. You finished with "
                     f"{count} — the new month's board is open, and the top inviter wins {PRIZE_LABEL}.",
                     "system", "/referrals", email=False)
    return {"month": month, "status": "awarded", "winner": name, "invites": invites,
            "prize": item, "order_id": order_id}


async def notify_city_waitlist(city: str) -> int:
    """Emails everyone waiting on a city the day it opens. One email per address, ever."""
    if not await db.events.count_documents({"city": city, "status": "published"}):
        return 0
    pending = await db.city_waitlist.find({"city": city,
                                           "notified_at": {"$in": [None, ""]}}).limit(1000).to_list(1000)
    if not pending:
        return 0
    slug = city_slug(city)
    country = country_for_city(city) or {}
    live = await db.events.count_documents({"city": city, "status": "published"})
    for w in pending:
        ok = await send_tpl("city_live", w["email"], {
            "city": city, "event_count": live, "currency": country.get("currency", BASE_CURRENCY),
            "city_url": f"{FRONTEND_URL}/city/{slug}"})
        await db.city_waitlist.update_one({"_id": w["_id"]},
                                          {"$set": {"notified_at": iso(now_utc()), "email_sent": ok}})
    logger.info(f"city waitlist: emailed {len(pending)} people about {city}")
    return len(pending)


async def open_city_waitlists() -> dict:
    cities = await db.city_waitlist.distinct("city", {"notified_at": {"$in": [None, ""]}})
    sent = {c: await notify_city_waitlist(c) for c in cities}
    return {"cities": [c for c, n in sent.items() if n], "emails": sum(sent.values())}


@api.post("/cron/monthly-prize")
async def cron_monthly_prize(_: None = Depends(cron_guard)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    asyncio.create_task(award_monthly_prize())
    return {"ok": True, "queued": "monthly-prize", "month": last_month()}


async def send_doors_open_nudges() -> int:
    """An hour before doors, nudges every pass holder — and the organiser with the arrival count."""
    now = now_utc()
    rows = await db.passes.find({"status": {"$in": ["valid", "redeemed"]}, "kind": "event",
                                 "starts_at": {"$gte": iso(now), "$lte": iso(now + timedelta(hours=1))},
                                 "doors_nudged": {"$ne": True}}).limit(1000).to_list(1000)
    sent, events = 0, {}
    for p in rows:
        await db.passes.update_one({"_id": p["_id"]}, {"$set": {"doors_nudged": True}})
        events[p["ref_id"]] = events.get(p["ref_id"], 0) + 1
        if p["status"] != "valid" or not ObjectId.is_valid(p.get("user_id") or ""):
            continue
        await notify(p["user_id"], "Doors open soon",
                     f"{p['item_name']} starts within the hour. Have code {p['code']} or your QR ready "
                     "at the door.", "reminder", "/orders", email=False)
        sent += 1
    for event_id in events:
        ev = await db.events.find_one({"_id": as_oid(event_id, "event")},
                                     {"title": 1, "partner_id": 1}) if ObjectId.is_valid(event_id) else None
        if not ev or not ev.get("partner_id"):
            continue
        items = await db.passes.find({"kind": "event", "ref_id": event_id}).limit(1000).to_list(1000)
        guests = sum(int(r.get("quantity") or 1) for r in items)
        arrived = sum(int(r.get("quantity") or 1) for r in items if r["status"] == "redeemed")
        await notify(ev["partner_id"], "Doors open within the hour",
                     f"{ev['title']}: {arrived} of {guests} guests have arrived. Open door check-in to "
                     "scan the rest.", "reminder", "/door", email=False)
    logger.info(f"doors-open nudges sent: {sent}")
    return sent


@api.post("/cron/city-openings")
async def cron_city_openings(_: None = Depends(cron_guard)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    asyncio.create_task(open_city_waitlists())
    asyncio.create_task(send_pass_reminders())
    asyncio.create_task(send_doors_open_nudges())
    return {"ok": True, "queued": ["city-openings", "pass-reminders", "doors-open-nudges"]}


def city_slug(name: str) -> str:
    out = "".join(ch if ch.isalnum() else "-" for ch in (name or "").lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def find_city(slug: str) -> tuple[str, dict]:
    for c in COUNTRIES:
        for city in c["cities"]:
            if city_slug(city) == slug:
                return city, c
    raise HTTPException(status_code=404, detail="Buddilio isn't in that city yet.")


def short_name(full: str) -> str:
    parts = [p for p in (full or "").split(" ") if p]
    if not parts:
        return "Member"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0]}."


@api.get("/cities")
async def list_city_pages():
    ev_counts = {d["_id"]: d["n"] for d in await db.events.aggregate(
        [{"$match": {"status": "published"}}, {"$group": {"_id": "$city", "n": {"$sum": 1}}}]).to_list(500)}
    mem_counts = {d["_id"]: d["n"] for d in await db.users.aggregate(
        [{"$match": {"role": "user", "status": "active"}}, {"$group": {"_id": "$city", "n": {"$sum": 1}}}]).to_list(500)}
    items = []
    for c in COUNTRIES:
        for city in c["cities"]:
            events = ev_counts.get(city, 0)
            items.append({"name": city, "slug": city_slug(city), "country": c["name"],
                          "country_code": c["code"], "currency": c["currency"],
                          "events": events, "members": mem_counts.get(city, 0), "live": events > 0})
    items.sort(key=lambda i: (-i["events"], i["name"]))
    return {"items": items, "cities": len(items), "countries": len(COUNTRIES),
            "live_cities": sum(1 for i in items if i["live"])}


async def city_hosts(city: str) -> dict:
    """Public teaser for approved companions in a city — counts and rate range only."""
    docs = await db.users.find({"role": "user", "status": "active", "verified": True,
                                "companion.status": "approved", "companion.enabled": True,
                                "companion.city": city},
                               {"full_name": 1, "photo": 1, "companion": 1}).limit(50).to_list(50)
    rates = [float((d.get("companion") or {}).get("hourly_rate") or 0) for d in docs]
    rates = [r for r in rates if r > 0]
    return {"count": len(docs), "from_rate": min(rates) if rates else 0,
            "to_rate": max(rates) if rates else 0,
            "faces": [{"name": short_name(d.get("full_name", "")), "photo": d.get("photo", "")}
                      for d in docs if d.get("photo")][:6]}


@api.get("/cities/{slug}")
async def city_page(slug: str):
    city, country = find_city(slug)
    stamp = iso(now_utc())
    upcoming = await db.events.find({"city": city, "status": "published", "starts_at": {"$gte": stamp}}) \
        .sort([("starts_at", 1)]).limit(6).to_list(6)
    published = await db.events.find({"city": city, "status": {"$in": ["published", "completed"]}},
                                     {"_id": 1, "cover_image": 1, "category": 1, "starts_at": 1}).limit(300).to_list(300)
    ids = [str(e["_id"]) for e in published]
    reviews = await db.reviews.find({"event_id": {"$in": ids}, "status": {"$ne": "hidden"},
                                     "comment": {"$nin": ["", None]}}) \
        .sort([("rating", -1), ("created_at", -1)]).limit(2).to_list(2)
    authors = await load_many(db.users, [r["user_id"] for r in reviews], {"full_name": 1})
    quotes = [{"rating": r["rating"], "comment": r["comment"],
               "user_name": short_name((authors.get(r["user_id"]) or {}).get("full_name", ""))}
              for r in reviews]
    faces = [{"id": str(u["_id"]), "name": short_name(u.get("full_name", "")), "photo": u.get("photo", "")}
             for u in await db.users.find({"city": city, "role": "user", "status": "active",
                                           "photo": {"$nin": ["", None]}},
                                          {"full_name": 1, "photo": 1}).limit(8).to_list(8)]
    hero = next((e.get("cover_image") for e in upcoming if e.get("cover_image")), "") \
        or next((e.get("cover_image") for e in published if e.get("cover_image")), "")
    return {
        "name": city, "slug": slug, "country": country["name"], "country_code": country["code"],
        "currency": country["currency"], "tax_label": country["tax_label"],
        "tax_percent": country["tax_percent"], "emergency": country["emergency"],
        "hero": hero, "upcoming": [clean(e) for e in upcoming],
        "events_total": len(ids),
        "past_events": sum(1 for e in published if e.get("starts_at", "") < stamp),
        "members": await db.users.count_documents({"city": city, "role": "user", "status": "active"}),
        "organisers": await db.users.count_documents({"city": city, "role": "partner"}),
        "categories": sorted({e.get("category", "") for e in published if e.get("category")}),
        "guide": await city_guide(city),
        "hosts": await city_hosts(city),
        "passes": [clean(p) for p in await db.products.find(
            {"active": True, "city": {"$in": [city, "Global", "All India"]}}).limit(4).to_list(4)],
        "faces": faces, "quotes": quotes,
        "waiting": await db.city_waitlist.count_documents({"city": city}),
        "nearby": [{"name": n, "slug": city_slug(n)} for n in country["cities"] if n != city][:6],
    }


@api.post("/cities/{slug}/waitlist")
async def join_city_waitlist(slug: str, body: dict):
    city, _ = find_city(slug)
    email = (body.get("email") or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    live = await db.events.count_documents({"city": city, "status": "published"})
    await db.city_waitlist.update_one(
        {"city": city, "email": email},
        {"$set": {"city": city, "email": email, "updated_at": iso(now_utc())},
         "$setOnInsert": {"created_at": iso(now_utc())}}, upsert=True)
    message = (f"Buddilio is already live in {city} — go and see what's on."
               if live else f"You're on the list for {city} — we'll email you the moment we open.")
    return {"message": message, "live": live > 0,
            "waiting": await db.city_waitlist.count_documents({"city": city})}


@api.get("/meta")
async def meta():
    extra = await db.cities.find({}).limit(300).to_list(300)
    cats = await db.event_categories.find({}).limit(100).to_list(100)
    ints = await db.interests.find({}).limit(200).to_list(200)
    conf = await currency_config()
    countries = []
    for c in COUNTRIES:
        cities = list(c["cities"])
        for e in extra:
            if e.get("country_code") == c["code"] and e["name"] not in cities:
                cities.append(e["name"])
        countries.append({**c, "cities": sorted(cities), "primary_city": c["cities"][0]})
    return {"countries": countries,
            "cities": [city for c in countries for city in c["cities"]],
            "base_currency": BASE_CURRENCY,
            "categories": [c["name"] for c in cats],
            "interests": [i["name"] for i in ints],
            "currencies": [{"code": k, **conf[k]} for k in DISPLAY_CURRENCIES if k in conf],
            "settings": clean(await db.settings.find_one({}) or {"_id": ObjectId(), "platform_name": "Buddilio"})}


class CountryIn(BaseModel):
    code: str
    name: str
    currency: str = BASE_CURRENCY
    tax_percent: float = 0
    tax_label: str = "Tax"
    emergency: str = ""
    cities: List[str] = []
    active: bool = True


@api.get("/admin/countries")
async def admin_countries(user: dict = Depends(require_perm("content:manage"))):
    rows = await db.countries.find({}).sort("name", 1).to_list(500)
    conf = await currency_config()
    return {"items": [clean(r) for r in rows], "currencies": sorted(conf.keys())}


@api.post("/admin/countries")
async def create_country(payload: CountryIn, user: dict = Depends(require_perm("content:manage"))):
    code = payload.code.strip().upper()[:2]
    if len(code) != 2 or not payload.name.strip():
        raise HTTPException(status_code=400, detail="A country needs a two-letter code and a name.")
    if await db.countries.find_one({"code": code}):
        raise HTTPException(status_code=400, detail="That country is already on the list.")
    doc = payload.dict() | {"code": code, "name": payload.name.strip()[:60],
                            "currency": payload.currency.strip().upper()[:3],
                            "cities": clean_city_list(payload.cities),
                            "created_at": iso(now_utc())}
    res = await db.countries.insert_one(doc)
    await refresh_countries()
    await audit(user, "country.create", "country", code, {"name": doc["name"]})
    return clean(await db.countries.find_one({"_id": res.inserted_id}))


@api.put("/admin/countries/{code}")
async def update_country(code: str, payload: CountryIn, user: dict = Depends(require_perm("content:manage"))):
    row = await db.countries.find_one({"code": code.upper()})
    if not row:
        raise HTTPException(status_code=404, detail="Country not found")
    upd = {"name": payload.name.strip()[:60], "currency": payload.currency.strip().upper()[:3],
           "tax_percent": float(payload.tax_percent), "tax_label": payload.tax_label[:30] or "Tax",
           "emergency": payload.emergency[:12], "cities": clean_city_list(payload.cities),
           "active": payload.active, "updated_at": iso(now_utc())}
    await db.countries.update_one({"_id": row["_id"]}, {"$set": upd})
    await refresh_countries()
    await audit(user, "country.update", "country", code.upper(), {"cities": len(upd["cities"])})
    return clean(await db.countries.find_one({"_id": row["_id"]}))


@api.delete("/admin/countries/{code}")
async def delete_country(code: str, user: dict = Depends(require_perm("content:manage"))):
    row = await db.countries.find_one({"code": code.upper()})
    if not row:
        raise HTTPException(status_code=404, detail="Country not found")
    live = await db.events.count_documents({"city": {"$in": row.get("cities") or []},
                                            "status": "published"})
    if live:
        raise HTTPException(status_code=400,
                            detail=f"{live} published events still run in this country — move them first.")
    await db.countries.delete_one({"_id": row["_id"]})
    await refresh_countries()
    await audit(user, "country.delete", "country", code.upper(), {"name": row.get("name", "")})
    return {"ok": True}


def clean_city_list(cities: List[str]) -> list:
    out = []
    for c in cities[:200]:
        name = str(c).strip()[:60]
        if name and name not in out:
            out.append(name)
    return out


@api.get("/cms/{slug}")
async def cms_page(slug: str):
    doc = await db.cms_pages.find_one({"slug": slug, "status": {"$ne": "draft"}})
    if not doc:
        raise HTTPException(status_code=404, detail="Page not found")
    out = clean(doc)
    out["blocks"] = out.get("blocks") or []
    return out


@api.get("/cms")
async def cms_pages():
    docs = await db.cms_pages.find({"status": {"$ne": "draft"}}).limit(100).to_list(100)
    return {"items": [clean(d) for d in docs]}


# ---------------- admin ----------------
@api.get("/admin/stats")
async def admin_stats(days: int = 30, user: dict = Depends(require_perm("analytics:view"))):
    since = iso(now_utc() - timedelta(days=days))
    paid = await db.orders.find({"payment_status": "paid", "created_at": {"$gte": since}}).limit(2000).to_list(2000)
    rates = await fx_rates()

    def base(o: dict) -> float:
        return float(o.get("total") or 0) / (rates.get((o.get("currency") or BASE_CURRENCY).upper()) or 1.0)

    def rev(kind):
        return round(sum(base(o) for o in paid if o["kind"] == kind), 2)
    users_total = await db.users.count_documents({"role": "user"})
    series = {}
    for o in paid:
        series[o["created_at"][:10]] = round(series.get(o["created_at"][:10], 0) + base(o), 2)
    reg_series = {}
    for u in await db.users.find({"created_at": {"$gte": since}}, {"created_at": 1}).limit(2000).to_list(2000):
        reg_series[u["created_at"][:10]] = reg_series.get(u["created_at"][:10], 0) + 1
    return {
        "total_users": users_total,
        "new_users": await db.users.count_documents({"role": "user", "created_at": {"$gte": since}}),
        "active_users": await db.users.count_documents({"role": "user", "status": "active"}),
        "premium_members": await db.user_memberships.count_documents({"status": "active"}),
        "partners": await db.users.count_documents({"role": "partner"}),
        "events": await db.events.count_documents({}),
        "upcoming_events": await db.events.count_documents({"status": "published", "starts_at": {"$gte": iso(now_utc())}}),
        "participations": await db.event_participants.count_documents({}),
        "gross_sales": round(sum(base(o) for o in paid), 2), "currency": BASE_CURRENCY,
        "membership_revenue": rev("membership"), "event_revenue": rev("event"), "pass_revenue": rev("product"),
        "refunds": await db.orders.count_documents({"refund_status": {"$in": ["requested", "refunded"]}}),
        "pending_events": await db.events.count_documents({"status": "submitted"}),
        "open_reports": await db.reports.count_documents({"status": "open"}),
        "flagged_reviews": await db.reviews.count_documents({"flag_count": {"$gt": 0}, "status": {"$ne": "hidden"}}),
        "revenue_series": [{"date": k, "amount": v} for k, v in sorted(series.items())],
        "registration_series": [{"date": k, "count": v} for k, v in sorted(reg_series.items())],
    }


def mask_email(value: str) -> str:
    """Admin lists show ta••@g••.com — the full address needs a deliberate, audited reveal."""
    email = (value or "").strip()
    if "@" not in email:
        return "•" * len(email)
    name, _, domain = email.partition("@")
    host, _, tld = domain.rpartition(".")
    return f"{name[:2]}{'•' * max(len(name) - 2, 2)}@{host[:1]}{'•' * max(len(host) - 1, 2)}" + (f".{tld}" if tld else "")


def mask_phone(value: str) -> str:
    digits = (value or "").strip()
    if len(digits) < 4:
        return "•" * len(digits)
    return f"{digits[:2]}{'•' * (len(digits) - 4)}{digits[-2:]}"


def masked_user(doc: dict) -> dict:
    doc["email"] = mask_email(doc.get("email", ""))
    doc["mobile"] = mask_phone(doc.get("mobile", ""))
    doc["pii_masked"] = True
    return doc


@api.get("/admin/users")
async def admin_users(q: str = "", role: str = "", status: str = "",
                      page: int = 1, limit: int = 20, user: dict = Depends(require_perm("members:view"))):
    flt: dict[str, Any] = {}
    if q:
        flt["$or"] = [{"full_name": {"$regex": q, "$options": "i"}}, {"email": {"$regex": q, "$options": "i"}}]
    if role:
        flt["role"] = role
    if status:
        flt["status"] = status
    total = await db.users.count_documents(flt)
    docs = await db.users.find(flt).sort([("created_at", -1)]).skip((page - 1) * limit).limit(limit).to_list(limit)
    items = []
    for d in docs:
        c = masked_user(clean(d))
        c["membership"] = await membership_active(c["id"])
        items.append(c)
    return {"items": items, "total": total, "page": page,
            "can_reveal": "team:manage" in perms_of(user)}


REVEAL_SECONDS = 10


@api.post("/admin/users/{uid}/reveal")
async def reveal_user_pii(uid: str, user: dict = Depends(require_perm("team:manage"))):
    """Super-admin only, logged every time, and the UI hides it again after ten seconds."""
    try:
        doc = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1, "mobile": 1, "full_name": 1})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid member id")
    if not doc:
        raise HTTPException(status_code=404, detail="Member not found")
    await audit(user, "user.pii_reveal", "user", uid, {"name": doc.get("full_name", "")})
    return {"email": doc.get("email", ""), "mobile": doc.get("mobile", ""),
            "seconds": REVEAL_SECONDS}


@api.post("/admin/users/{uid}/temp-password")
async def issue_temp_password(uid: str, user: dict = Depends(require_perm("team:manage"))):
    """Stored passwords are one-way hashes, so we mint a single-use one instead of exposing the old one."""
    try:
        doc = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1, "full_name": 1})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid member id")
    if not doc:
        raise HTTPException(status_code=404, detail="Member not found")
    temp = secrets.token_urlsafe(9) + "aA1!"
    await db.users.update_one({"_id": doc["_id"]}, {"$set": {
        "password_hash": hash_password(temp), "must_change_password": True,
        "password_reset_by": user["id"], "password_reset_at": iso(now_utc())}})
    await audit(user, "user.temp_password", "user", uid, {"name": doc.get("full_name", "")})
    await notify(uid, "Your password was reset",
                 "A Buddilio admin issued you a new temporary password. Change it the next time you sign in.",
                 "system", "/profile")
    return {"password": temp, "seconds": REVEAL_SECONDS, "must_change": True}


MASK_CHAR = "•"


def reject_masked(value: str, field: str = "email"):
    if MASK_CHAR in (value or ""):
        raise HTTPException(status_code=400,
                            detail=f"Reveal the {field} before saving it — masked values can't be stored.")


@api.patch("/admin/users/{uid}")
async def admin_update_user(uid: str, body: dict, user: dict = Depends(require_perm("members:manage"))):
    allowed = {k: v for k, v in body.items()
               if k in ("status", "verified", "role", "full_name", "city", "email_verified")}
    if not allowed:
        raise HTTPException(status_code=400, detail="Nothing to update")
    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": allowed})
    await audit(user, "user.update", "user", uid, allowed)
    return clean(await db.users.find_one({"_id": ObjectId(uid)}))


@api.get("/admin/events")
async def admin_events(status: str = "", user: dict = Depends(require_perm("events:view"))):
    flt = {"status": status} if status else {}
    docs = await db.events.find(flt).sort([("created_at", -1)]).limit(300).to_list(300)
    return {"items": [clean(d) for d in docs]}


@api.post("/admin/events/{eid}/moderate")
async def moderate_event(eid: str, body: dict, user: dict = Depends(require_perm("events:moderate"))):
    action = body.get("action")
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action")
    ev = await db.events.find_one({"_id": ObjectId(eid)})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    new_status = "published" if action == "approve" else "rejected"
    await db.events.update_one({"_id": ev["_id"]},
                               {"$set": {"status": new_status, "review_note": body.get("note", "")}})
    await audit(user, f"event.{action}", "event", eid, {"title": ev["title"]})
    if action == "approve" and ev.get("partner_id"):
        asyncio.create_task(notify_followers(ev["partner_id"], ev))
    if ev.get("partner_id"):
        await notify(ev["partner_id"], f"Event {new_status}",
                     f"{ev['title']} was {new_status} by the Buddilio team.", "event", "/partner")
    if new_status == "published":
        asyncio.create_task(notify_city_waitlist(ev["city"]))
    return {"status": new_status}


@api.get("/admin/orders")
async def admin_orders(status: str = "", user: dict = Depends(require_perm("finance:view"))):
    flt = {"payment_status": status} if status else {}
    return {"items": [clean(d) for d in await db.orders.find(flt).sort([("created_at", -1)]).limit(300).to_list(300)]}


async def refund_stripe(order: dict, amount: float) -> str:
    """Stripe refunds go against the payment intent captured at checkout."""
    key = os.environ.get("STRIPE_API_KEY", "")
    intent = order.get("transaction_id") or ""
    if not key or not intent.startswith(("pi_", "ch_", "cs_")):
        raise HTTPException(status_code=400,
                            detail="This card payment has no Stripe reference to refund. "
                                   "Refund it from the Stripe dashboard and record it here.")
    data = {"amount": int(round(amount * 100)), "reason": "requested_by_customer"}
    data["payment_intent" if intent.startswith("pi_") else "charge"] = intent
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post("https://api.stripe.com/v1/refunds", data=data, auth=(key, ""))
    if r.status_code >= 400:
        logger.error(f"Stripe refund failed for {order['order_no']}: {r.text[:300]}")
        raise HTTPException(status_code=502, detail="Stripe rejected this refund. Try the Stripe dashboard.")
    return r.json().get("id", "")


async def refund_paypal(order: dict, amount: float) -> str:
    """PayPal refunds go against the capture id stored on the order."""
    capture_id = order.get("transaction_id") or ""
    if not capture_id:
        raise HTTPException(status_code=400, detail="This PayPal payment has no capture reference to refund.")
    charged = float(order.get("charge_total_paypal") or order.get("charge_total") or order["total"])
    full = amount >= charged - 0.01
    try:
        res = await paypal.refund_capture(capture_id, None if full else amount,
                                          f"Buddilio order {order['order_no']}")
    except paypal.PayPalError as exc:
        logger.error(f"PayPal refund failed for {order['order_no']}: {exc}")
        raise HTTPException(status_code=502, detail=paypal.member_message(exc))
    return res.get("id", "")


class RefundIn(BaseModel):
    amount: float = 0.0
    reason: str = ""
    override_policy: bool = False   # superadmin goodwill exception, always audited


def refund_ceiling(order: dict) -> tuple[float, str]:
    """What the cancellation policy allows back — membership fees are never refundable."""
    base = float(order.get("charge_total") or order["total"])
    if order["kind"] == "membership":
        return 0.0, "Membership fees are non-refundable under the cancellation policy."
    quote = order.get("cancellation") or {}
    if quote.get("refundable") is not None and quote.get("status") in ("requested", "settled"):
        return round(float(quote["refundable"]), 2), (
            f"The cancellation policy allows {fmt_money(float(quote['refundable']), order.get('currency'))} "
            f"back after a {quote.get('deduction_percent', 0)}% deduction.")
    return base, ""


@api.post("/admin/orders/{oid}/refund")
async def refund_order(oid: str, payload: RefundIn = Body(default=RefundIn()),
                       user: dict = Depends(require_perm("finance:manage"))):
    order = await db.orders.find_one({"_id": as_oid(oid, "order")})
    if not order or order["payment_status"] != "paid":
        raise HTTPException(status_code=400, detail="Only paid orders can be refunded.")
    if order.get("refund_status") == "refunded":
        raise HTTPException(status_code=400, detail="This order has already been refunded.")
    base_total = float(order.get("charge_total") or order["total"])
    already = float(order.get("refunded_amount") or 0)
    amount = round(float(payload.amount or 0) or (base_total - already), 2)
    remaining = round(base_total - already, 2)
    if amount <= 0 or amount - remaining > 0.005:
        raise HTTPException(status_code=400,
                            detail=f"Enter an amount between 0 and {remaining:.2f}.")
    ceiling, policy_note = refund_ceiling(order)
    if not payload.override_policy and amount - round(ceiling - already, 2) > 0.005:
        raise HTTPException(status_code=400, detail=(
            f"{policy_note or 'The cancellation policy caps this refund.'} "
            "Tick 'override policy' with a reason to refund more."))
    if payload.override_policy and not payload.reason.strip():
        raise HTTPException(status_code=400,
                            detail="A reason is required when overriding the cancellation policy.")
    gateway_ref = ""
    gateway = order.get("gateway", "")
    client_rp = razorpay_client()
    if gateway == "paypal":
        usd = round(amount / base_total * float(order.get("charge_total_paypal") or amount), 2) \
            if order.get("charge_total_paypal") else amount
        gateway_ref = await refund_paypal(order, usd)
    elif gateway == "stripe":
        gateway_ref = await refund_stripe(order, amount)
    elif client_rp and gateway == "razorpay" and order.get("transaction_id"):
        try:
            rf = await asyncio.to_thread(client_rp.payment.refund, order["transaction_id"],
                                         {"amount": int(round(amount * 100)), "speed": "normal"})
            gateway_ref = rf.get("id", "")
        except Exception as e:
            logger.error(f"Razorpay refund failed: {e}")
            raise HTTPException(status_code=502, detail="The gateway rejected this refund. Please retry from the Razorpay dashboard.")
    refunded_total = round(already + amount, 2)
    partial = refunded_total < base_total - 0.01
    await db.orders.update_one({"_id": order["_id"]}, {"$set": {
        "refund_status": "partial" if partial else "refunded",
        "order_status": order["order_status"] if partial else "refunded",
        "refund_id": gateway_ref, "refunded_amount": refunded_total,
        "refund_reason": payload.reason, "refunded_at": iso(now_utc())}})
    if not partial:
        if order["kind"] == "membership":
            await db.user_memberships.update_many({"order_id": oid}, {"$set": {"status": "cancelled"}})
        if order["kind"] == "event":
            part = await db.event_participants.find_one({"order_id": oid})
            if part:
                await db.event_participants.delete_one({"_id": part["_id"]})
                count = await db.event_participants.count_documents({"event_id": order["ref_id"], "status": "confirmed"})
                await db.events.update_one({"_id": ObjectId(order["ref_id"])}, {"$set": {"participant_count": count}})
    await audit(user, "order.refund", "order", oid,
                {"amount": amount, "refund_id": gateway_ref, "partial": partial, "gateway": gateway,
                 "policy_ceiling": ceiling, "override_policy": payload.override_policy,
                 "reason": payload.reason})
    await notify(order["user_id"], "Refund processed",
                 f"{fmt_money(amount, order.get('currency'))} for {order['item_name']} has been refunded. "
                 "It reaches your original payment method in 5-7 working days.", "refund", "/orders")
    await send_tpl("order_refunded", order.get("user_email", ""),
                   {"first_name": first_name(order.get("user_name", "")),
                    "item": order["item_name"], "order_no": order["order_no"],
                    "amount": fmt_money(amount, order.get("currency")),
                    "orders_url": f"{FRONTEND_URL}/orders"})
    return {"refund_status": "partial" if partial else "refunded", "refund_id": gateway_ref,
            "refunded_amount": refunded_total, "amount": amount}


@api.post("/me/orders/{oid}/retry")
async def retry_order(oid: str, user: dict = Depends(get_current_user)):
    """Re-opens a failed or pending order so the member can pay again."""
    order = await db.orders.find_one({"_id": as_oid(oid, "order"), "user_id": user["id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    if order["payment_status"] == "paid":
        raise HTTPException(status_code=400, detail="This order is already paid.")
    await db.orders.update_one({"_id": order["_id"]}, {"$set": {
        "payment_status": "pending", "order_status": "created", "failure_reason": "",
        "gateway_order_id": "", "retried_at": iso(now_utc())},
        "$inc": {"retry_count": 1}})
    fresh = await db.orders.find_one({"_id": order["_id"]})
    return {"order": clean(fresh)}


@api.get("/admin/reports")
async def admin_reports(status: str = "", user: dict = Depends(require_perm("moderation:manage"))):
    flt = {"status": status} if status else {}
    docs = await db.reports.find(flt).sort([("created_at", -1)]).limit(300).to_list(300)
    out = []
    for d in docs:
        r = clean(d)
        if r["target_type"] == "user":
            try:
                t = await db.users.find_one({"_id": ObjectId(r["target_id"])}, {"full_name": 1, "email": 1, "status": 1})
                r["target"] = clean(t) if t else None
            except Exception:
                r["target"] = None
        out.append(r)
    return {"items": out}


@api.post("/admin/reports/{rid}/resolve")
async def resolve_report(rid: str, body: dict, user: dict = Depends(require_perm("moderation:manage"))):
    action = body.get("action", "dismiss")  # dismiss | suspend | ban
    rep = await db.reports.find_one({"_id": ObjectId(rid)})
    if not rep:
        raise HTTPException(status_code=404, detail="Report not found")
    if action in ("suspend", "ban") and rep["target_type"] == "user":
        await db.users.update_one({"_id": ObjectId(rep["target_id"])},
                                  {"$set": {"status": "suspended" if action == "suspend" else "banned"}})
    await db.reports.update_one({"_id": rep["_id"]},
                                {"$set": {"status": "resolved", "resolution": action,
                                          "resolved_at": iso(now_utc())}})
    await audit(user, f"report.{action}", "report", rid, {})
    return {"status": "resolved", "action": action}


@api.get("/admin/audit-logs")
async def audit_logs(user: dict = Depends(require_perm("audit:view"))):
    return {"items": [clean(d) for d in await db.audit_logs.find({}).sort([("created_at", -1)]).limit(200).to_list(200)]}


def crud_routes(path: str, coll: str, model):
    @api.post(f"/admin/{path}", name=f"create_{path}")
    async def create(payload: model, user: dict = Depends(require_perm("finance:manage"))):  # type: ignore
        doc = payload.model_dump()
        if "code" in doc:
            doc["code"] = doc["code"].upper()
        doc["created_at"] = iso(now_utc())
        res = await db[coll].insert_one(doc)
        await audit(user, f"{path}.create", path, str(res.inserted_id), {})
        return clean(await db[coll].find_one({"_id": res.inserted_id}))

    @api.get(f"/admin/{path}", name=f"list_{path}")
    async def listing(user: dict = Depends(require_perm("finance:view", "finance:manage"))):
        return {"items": [clean(d) for d in await db[coll].find({}).limit(200).to_list(200)]}

    @api.put(f"/admin/{path}/{{item_id}}", name=f"update_{path}")
    async def update(item_id: str, payload: model, user: dict = Depends(require_perm("finance:manage"))):  # type: ignore
        await db[coll].update_one({"_id": ObjectId(item_id)}, {"$set": payload.model_dump()})
        await audit(user, f"{path}.update", path, item_id, {})
        return clean(await db[coll].find_one({"_id": ObjectId(item_id)}))

    @api.delete(f"/admin/{path}/{{item_id}}", name=f"delete_{path}")
    async def delete(item_id: str, user: dict = Depends(require_perm("finance:manage"))):
        await db[coll].delete_one({"_id": ObjectId(item_id)})
        await audit(user, f"{path}.delete", path, item_id, {})
        return {"ok": True}


crud_routes("plans", "membership_plans", PlanIn)
crud_routes("products", "products", ProductIn)
crud_routes("coupons", "coupons", CouponIn)


@api.put("/admin/cms/{slug}")
async def update_cms(slug: str, body: dict, user: dict = Depends(require_perm("content:manage"))):
    await db.cms_pages.update_one({"slug": slug},
                                  {"$set": {"title": body.get("title", slug),
                                            "content": safe_html(body.get("content", ""))[:20000],
                                            "seo_title": body.get("seo_title", ""),
                                            "seo_description": body.get("seo_description", ""),
                                            "updated_at": iso(now_utc())}}, upsert=True)
    await audit(user, "cms.update", "cms_page", slug, {})
    return clean(await db.cms_pages.find_one({"slug": slug}))


@api.get("/admin/settings")
async def get_settings(user: dict = Depends(require_perm("content:manage"))):
    return clean(await db.settings.find_one({}))


@api.put("/admin/settings")
async def update_settings(body: dict, user: dict = Depends(require_perm("content:manage"))):
    body.pop("id", None)
    s = await db.settings.find_one({})
    await db.settings.update_one({"_id": s["_id"]}, {"$set": body})
    await audit(user, "settings.update", "settings", str(s["_id"]), {})
    return clean(await db.settings.find_one({}))


@api.post("/uploads")
async def upload_image(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    ext = (file.filename or "img.jpg").rsplit(".", 1)[-1].lower()
    if ext not in MIME_TYPES:
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG, WEBP or GIF image.")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Images must be under 5MB.")
    content_type = file.content_type or MIME_TYPES[ext]
    path = f"{APP_NAME}/uploads/{user['id']}/{uuid.uuid4()}.{ext}"
    try:
        result = await asyncio.to_thread(put_object, path, data, content_type)
    except Exception as e:
        logger.error(f"upload failed: {e}")
        raise HTTPException(status_code=502, detail="Upload failed. Please try again.")
    await db.files.insert_one({"storage_path": result["path"], "owner_id": user["id"],
                               "original_filename": file.filename, "content_type": content_type,
                               "size": result.get("size", len(data)), "is_deleted": False,
                               "created_at": iso(now_utc())})
    return {"url": f"/api/files/{result['path']}", "path": result["path"], "size": result.get("size", len(data))}


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024
CHUNK_LIMIT_BYTES = 3 * 1024 * 1024


async def register_file(user_id: str, result: dict, filename: str, content_type: str, size: int) -> dict:
    await db.files.insert_one({"storage_path": result["path"], "owner_id": user_id,
                               "original_filename": filename, "content_type": content_type,
                               "size": result.get("size", size), "is_deleted": False,
                               "created_at": iso(now_utc())})
    return {"url": f"/api/files/{result['path']}", "path": result["path"],
            "name": filename, "content_type": content_type, "size": result.get("size", size)}


def upload_ext(filename: str, allowed: dict) -> str:
    ext = (filename or "file.bin").rsplit(".", 1)[-1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400,
                            detail=f"That file type isn't supported. Allowed: {', '.join(sorted(allowed))}.")
    return ext


@api.post("/uploads/file")
async def upload_any(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Images, PDFs, docs, short audio/video — one shot. Bigger files use the chunked endpoints."""
    ext = upload_ext(file.filename, ALL_MIME_TYPES)
    data = await file.read()
    cap = MAX_IMAGE_BYTES if ext in MIME_TYPES else 10 * 1024 * 1024
    if len(data) > cap:
        raise HTTPException(status_code=400, detail=f"That file is too large. Limit is {cap // (1024 * 1024)}MB.")
    content_type = file.content_type or ALL_MIME_TYPES[ext]
    path = f"{APP_NAME}/uploads/{user['id']}/{uuid.uuid4()}.{ext}"
    try:
        result = await asyncio.to_thread(put_object, path, data, content_type)
    except Exception as e:
        logger.error(f"upload failed: {e}")
        raise HTTPException(status_code=502, detail="Upload failed. Please try again.")
    return await register_file(user["id"], result, file.filename or f"file.{ext}", content_type, len(data))


class ChunkInitIn(BaseModel):
    filename: str
    size: int
    content_type: str = ""


@api.post("/uploads/chunk/init")
async def upload_chunk_init(payload: ChunkInitIn, user: dict = Depends(get_current_user)):
    """Chunked upload so large media isn't cut off by proxy body limits."""
    ext = upload_ext(payload.filename, ALL_MIME_TYPES)
    if payload.size <= 0 or payload.size > MAX_FILE_BYTES:
        raise HTTPException(status_code=400,
                            detail=f"Files must be under {MAX_FILE_BYTES // (1024 * 1024)}MB.")
    upload_id = uuid.uuid4().hex
    await db.upload_sessions.insert_one({
        "upload_id": upload_id, "owner_id": user["id"], "filename": payload.filename,
        "content_type": payload.content_type or ALL_MIME_TYPES[ext], "ext": ext,
        "size": payload.size, "received": 0, "created_at": iso(now_utc())})
    return {"upload_id": upload_id, "chunk_size": CHUNK_LIMIT_BYTES}


@api.post("/uploads/chunk/part")
async def upload_chunk_part(upload_id: str = Form(...), index: int = Form(...),
                            chunk: UploadFile = File(...), user: dict = Depends(get_current_user)):
    sess = await db.upload_sessions.find_one({"upload_id": upload_id, "owner_id": user["id"]})
    if not sess:
        raise HTTPException(status_code=404, detail="That upload session has expired. Please try again.")
    data = await chunk.read()
    if len(data) > CHUNK_LIMIT_BYTES:
        raise HTTPException(status_code=400, detail="Chunk too large.")
    if sess["received"] + len(data) > sess["size"] + CHUNK_LIMIT_BYTES:
        raise HTTPException(status_code=400, detail="Upload exceeded the declared file size.")
    await db.upload_parts.update_one({"upload_id": upload_id, "index": index},
                                    {"$set": {"data": data, "created_at": iso(now_utc())}}, upsert=True)
    # recount rather than $inc so a retried chunk doesn't inflate the total
    parts = await db.upload_parts.find({"upload_id": upload_id}, {"data": 1}).limit(200).to_list(200)
    received = sum(len(p["data"]) for p in parts)
    await db.upload_sessions.update_one({"_id": sess["_id"]}, {"$set": {"received": received}})
    return {"ok": True, "index": index, "received": received}


@api.post("/uploads/chunk/complete")
async def upload_chunk_complete(upload_id: str = Form(...), user: dict = Depends(get_current_user)):
    sess = await db.upload_sessions.find_one({"upload_id": upload_id, "owner_id": user["id"]})
    if not sess:
        raise HTTPException(status_code=404, detail="That upload session has expired. Please try again.")
    parts = await db.upload_parts.find({"upload_id": upload_id}).sort("index", 1).limit(200).to_list(200)
    body = b"".join(p["data"] for p in parts)
    await db.upload_parts.delete_many({"upload_id": upload_id})
    await db.upload_sessions.delete_one({"_id": sess["_id"]})
    if not body:
        raise HTTPException(status_code=400, detail="No file data was received. Please try again.")
    if len(body) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="That file is too large.")
    path = f"{APP_NAME}/uploads/{user['id']}/{uuid.uuid4()}.{sess['ext']}"
    try:
        result = await asyncio.to_thread(put_object, path, body, sess["content_type"])
    except Exception as e:
        logger.error(f"chunked upload failed: {e}")
        raise HTTPException(status_code=502, detail="Upload failed. Please try again.")
    return await register_file(user["id"], result, sess["filename"], sess["content_type"], len(body))


@api.get("/me/files")
async def my_files(user: dict = Depends(get_current_user)):
    docs = await db.files.find({"owner_id": user["id"], "is_deleted": False},
                               {"storage_path": 1, "original_filename": 1, "content_type": 1,
                                "size": 1, "created_at": 1}).sort("created_at", -1).limit(100).to_list(100)
    return {"items": [{"path": d["storage_path"], "url": f"/api/files/{d['storage_path']}",
                       "name": d.get("original_filename", ""), "content_type": d.get("content_type", ""),
                       "size": d.get("size", 0), "created_at": d.get("created_at", "")} for d in docs]}


@api.delete("/uploads")
async def delete_upload(path: str, user: dict = Depends(get_current_user)):
    """Storage has no delete API, so this is a soft delete — the file stops being served."""
    if not path.startswith(f"{APP_NAME}/uploads/"):
        raise HTTPException(status_code=400, detail="Invalid file path")
    rec = await db.files.find_one({"storage_path": path})
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")
    if rec.get("owner_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="You can only remove your own files.")
    await db.files.update_one({"_id": rec["_id"]},
                              {"$set": {"is_deleted": True, "deleted_at": iso(now_utc())}})
    return {"ok": True}


@api.get("/files/{path:path}")
async def serve_file(path: str):
    rec = await db.files.find_one({"storage_path": path, "is_deleted": False})
    if not rec:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data, content_type = await asyncio.to_thread(get_object, path)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(content=data, media_type=rec.get("content_type", content_type),
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


# ---------------- reviews ----------------
VISIBLE_REVIEW = {"status": {"$ne": "hidden"}}


async def recompute_ratings(event_id: str, partner_id: str = "") -> tuple[float, int]:
    revs = await db.reviews.find({"event_id": event_id, **VISIBLE_REVIEW}, {"rating": 1}).limit(1000).to_list(1000)
    avg = round(sum(r["rating"] for r in revs) / len(revs), 2) if revs else 0
    await db.events.update_one({"_id": ObjectId(event_id)},
                               {"$set": {"rating": avg, "rating_count": len(revs)}})
    if partner_id:
        pr = await db.reviews.find({"partner_id": partner_id, **VISIBLE_REVIEW}, {"rating": 1}).limit(5000).to_list(5000)
        await db.users.update_one({"_id": ObjectId(partner_id)},
                                  {"$set": {"rating": round(sum(r["rating"] for r in pr) / len(pr), 2) if pr else 0,
                                            "rating_count": len(pr)}})
    return avg, len(revs)


async def review_or_404(rid: str) -> dict:
    try:
        rev = await db.reviews.find_one({"_id": ObjectId(rid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid review id")
    if not rev:
        raise HTTPException(status_code=404, detail="Review not found")
    return rev


async def review_author(r: dict) -> dict:
    u = await db.users.find_one({"_id": ObjectId(r["user_id"])}, {"full_name": 1, "photo": 1, "email": 1})
    r["user_name"] = u["full_name"] if u else "Member"
    r["user_photo"] = u.get("photo", "") if u else ""
    r["user_email"] = u.get("email", "") if u else ""
    return r


@api.get("/events/{event_id}/reviews")
async def list_reviews(event_id: str, user: Optional[dict] = Depends(optional_user)):
    is_admin = bool(user and user.get("role") == "admin")
    flt = {"event_id": event_id} if is_admin else {"event_id": event_id, **VISIBLE_REVIEW}
    docs = await db.reviews.find(flt).sort([("created_at", -1)]).limit(100).to_list(100)
    out = []
    for d in docs:
        r = await review_author(clean(d))
        r.pop("user_email", None)
        r["mine"] = bool(user and r["user_id"] == user["id"])
        out.append(r)
    visible = [r for r in out if r.get("status") != "hidden"]
    avg = round(sum(r["rating"] for r in visible) / len(visible), 2) if visible else 0
    return {"items": out, "average": avg, "count": len(visible)}


@api.post("/events/{event_id}/reviews")
async def create_review(event_id: str, payload: ReviewIn, user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"_id": ObjectId(event_id)})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    ended = ev.get("ends_at") or ev["starts_at"]
    if ended > iso(now_utc()):
        raise HTTPException(status_code=400, detail="You can review this experience once it has finished.")
    part = await db.event_participants.find_one({"event_id": event_id, "user_id": user["id"], "status": "confirmed"})
    if not part:
        raise HTTPException(status_code=403, detail="Only confirmed attendees can review this experience.")
    if await db.reviews.find_one({"event_id": event_id, "user_id": user["id"]}):
        raise HTTPException(status_code=400, detail="You have already reviewed this experience.")
    await db.reviews.insert_one({"event_id": event_id, "user_id": user["id"], "partner_id": ev.get("partner_id", ""),
                                 "rating": payload.rating, "comment": payload.comment.strip()[:1000],
                                 "status": "published", "flag_count": 0, "flagged": False, "reply": None,
                                 "created_at": iso(now_utc())})
    avg, count = await recompute_ratings(event_id, ev.get("partner_id", ""))
    if ev.get("partner_id"):
        await notify(ev["partner_id"], "New review",
                     f"{user['full_name']} rated {ev['title']} {payload.rating}/5.", "event", "/partner")
    return {"average": avg, "count": count}


@api.get("/me/reviewable")
async def reviewable(user: dict = Depends(get_current_user)):
    parts = await db.event_participants.find({"user_id": user["id"], "status": "confirmed"}).limit(200).to_list(200)
    out = []
    for p in parts:
        if await db.reviews.find_one({"event_id": p["event_id"], "user_id": user["id"]}):
            continue
        try:
            ev = await db.events.find_one({"_id": ObjectId(p["event_id"])})
        except Exception:
            continue
        if ev and (ev.get("ends_at") or ev["starts_at"]) < iso(now_utc()):
            out.append(clean(ev))
    return {"items": out}


@api.post("/reviews/{rid}/report")
async def report_review(rid: str, body: dict, user: dict = Depends(get_current_user)):
    rev = await review_or_404(rid)
    if rev["user_id"] == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot report your own review.")
    if await db.reports.find_one({"target_type": "review", "target_id": rid, "reporter_id": user["id"]}):
        raise HTTPException(status_code=400, detail="You have already reported this review.")
    reason = (body.get("reason") or "Inappropriate content").strip()[:200]
    await db.reports.insert_one({
        "reporter_id": user["id"], "reporter_email": user["email"], "target_type": "review",
        "target_id": rid, "reason": reason, "details": (body.get("details") or "").strip()[:500],
        "status": "open", "meta": {"event_id": rev["event_id"]}, "created_at": iso(now_utc())})
    await db.reviews.update_one({"_id": rev["_id"]}, {"$inc": {"flag_count": 1}, "$set": {"flagged": True}})
    admin = await db.users.find_one({"role": "admin"})
    if admin:
        await notify(str(admin["_id"]), "Review flagged",
                     f"A member reported a review: {reason}", "moderation", "/admin")
    return {"message": "Thanks — our safety team will look at this review."}


@api.post("/reviews/{rid}/reply")
async def reply_to_review(rid: str, body: dict, user: dict = Depends(partner_only)):
    rev = await review_or_404(rid)
    if user["role"] != "admin" and rev.get("partner_id") != user["id"]:
        raise HTTPException(status_code=403, detail="You can only reply to reviews on your own events.")
    text = (body.get("body") or "").strip()[:800]
    if not text:
        raise HTTPException(status_code=400, detail="Write a reply before posting it.")
    reply = {"body": text, "by": user["id"], "by_name": user.get("org_name") or user["full_name"],
             "at": iso(now_utc())}
    await db.reviews.update_one({"_id": rev["_id"]}, {"$set": {"reply": reply}})
    await notify(rev["user_id"], "The organiser replied to your review",
                 f"{reply['by_name']}: {text[:120]}", "event", f"/events/{rev['event_id']}", email=False)
    return {"reply": reply}


@api.get("/partner/reviews")
async def partner_reviews(user: dict = Depends(partner_only)):
    docs = await db.reviews.find({"partner_id": user["id"]}).sort([("created_at", -1)]).limit(300).to_list(300)
    out = []
    for d in docs:
        r = await review_author(clean(d))
        r.pop("user_email", None)
        try:
            ev = await db.events.find_one({"_id": ObjectId(r["event_id"])}, {"title": 1})
        except Exception:
            ev = None
        r["event_title"] = ev["title"] if ev else "Experience"
        out.append(r)
    visible = [r for r in out if r.get("status") != "hidden"]
    return {"items": out,
            "average": round(sum(r["rating"] for r in visible) / len(visible), 2) if visible else 0,
            "count": len(visible),
            "unanswered": sum(1 for r in visible if not r.get("reply"))}


@api.get("/admin/reviews")
async def admin_reviews(status: str = "", user: dict = Depends(require_perm("moderation:manage"))):
    if status == "flagged":
        flt: dict[str, Any] = {"flag_count": {"$gt": 0}, "status": {"$ne": "hidden"}}
    elif status:
        flt = {"status": status}
    else:
        flt = {}
    docs = await db.reviews.find(flt).sort([("flag_count", -1), ("created_at", -1)]).limit(300).to_list(300)
    events = await load_many(db.events, [d.get("event_id", "") for d in docs],
                             {"title": 1, "partner_name": 1})
    reports: dict[str, list] = {}
    for rp in await db.reports.find({"target_type": "review",
                                     "target_id": {"$in": [str(d["_id"]) for d in docs]}}).limit(1000).to_list(1000):
        reports.setdefault(rp["target_id"], []).append(rp)
    out = []
    for d in docs:
        r = await review_author(clean(d))
        ev = events.get(r["event_id"])
        r["event_title"] = ev["title"] if ev else "Experience"
        r["partner_name"] = (ev or {}).get("partner_name", "")
        r["reports"] = [{"reason": rp["reason"], "by": rp["reporter_email"], "at": rp["created_at"]}
                        for rp in reports.get(r["id"], [])[:20]]
        out.append(r)
    return {"items": out,
            "flagged": await db.reviews.count_documents({"flag_count": {"$gt": 0}, "status": {"$ne": "hidden"}}),
            "hidden": await db.reviews.count_documents({"status": "hidden"}),
            "total": await db.reviews.count_documents({})}


@api.post("/admin/reviews/{rid}/moderate")
async def moderate_review(rid: str, body: dict, user: dict = Depends(require_perm("moderation:manage"))):
    action = body.get("action")
    if action not in ("hide", "publish", "delete"):
        raise HTTPException(status_code=400, detail="Invalid action")
    rev = await review_or_404(rid)
    if action == "delete":
        await db.reviews.delete_one({"_id": rev["_id"]})
    elif action == "hide":
        await db.reviews.update_one({"_id": rev["_id"]},
                                   {"$set": {"status": "hidden", "moderation_note": (body.get("note") or "")[:300],
                                             "moderated_at": iso(now_utc())}})
    else:
        await db.reviews.update_one({"_id": rev["_id"]},
                                   {"$set": {"status": "published", "flag_count": 0, "flagged": False,
                                             "moderated_at": iso(now_utc())}})
    await db.reports.update_many({"target_type": "review", "target_id": rid, "status": "open"},
                                 {"$set": {"status": "resolved", "resolution": action,
                                           "resolved_at": iso(now_utc())}})
    await recompute_ratings(rev["event_id"], rev.get("partner_id", ""))
    await audit(user, f"review.{action}", "review", rid, {"event_id": rev["event_id"]})
    if action in ("hide", "delete"):
        await notify(rev["user_id"], "Your review was removed",
                     "One of your event reviews was removed because it did not meet our community guidelines.",
                     "moderation", "/dashboard", email=False)
    return {"status": action}


# ---------------- payouts ----------------
PLATFORM_FEE = float(os.environ.get("PLATFORM_FEE_PERCENT", "15"))
PAYOUT_HOLD_HOURS = int(os.environ.get("PAYOUT_HOLD_HOURS", "48"))


async def generate_payouts():
    """Marks finished events completed and creates one payout ledger row per event."""
    cutoff = iso(now_utc() - timedelta(hours=PAYOUT_HOLD_HOURS))
    events = await db.events.find({"status": {"$in": ["published", "completed"]},
                                   "$or": [{"ends_at": {"$lt": cutoff, "$ne": ""}},
                                           {"starts_at": {"$lt": cutoff}}]}).limit(500).to_list(500)
    created = 0
    for ev in events:
        eid = str(ev["_id"])
        if ev.get("status") == "published":
            await db.events.update_one({"_id": ev["_id"]}, {"$set": {"status": "completed"}})
        if not ev.get("partner_id") or await db.payouts.find_one({"event_id": eid}):
            continue
        orders = await db.orders.find({"kind": "event", "ref_id": eid, "payment_status": "paid",
                                       "refund_status": "none"}).limit(1000).to_list(1000)
        gross = round(sum(o["subtotal"] - o["discount"] for o in orders), 2)
        fee = round(gross * PLATFORM_FEE / 100, 2)
        await db.payouts.insert_one({
            "partner_id": ev["partner_id"], "event_id": eid, "event_title": ev["title"],
            "orders": len(orders), "gross": gross, "fee_percent": PLATFORM_FEE, "fee": fee,
            "net": round(gross - fee, 2), "currency": BASE_CURRENCY, "status": "pending",
            "created_at": iso(now_utc())})
        created += 1
        await notify(ev["partner_id"], "Payout ready",
                     f"Your payout for {ev['title']} ({fmt_money(round(gross - fee, 2))}) is queued for settlement.",
                     "order", "/partner")
    return created


@api.get("/partner/payouts")
async def partner_payouts(user: dict = Depends(partner_only)):
    docs = await db.payouts.find({"partner_id": user["id"]}).sort([("created_at", -1)]).limit(300).to_list(300)
    items = [clean(d) for d in docs]
    return {"items": items,
            "pending_total": round(sum(i["net"] for i in items if i["status"] == "pending"), 2),
            "paid_total": round(sum(i["net"] for i in items if i["status"] == "paid"), 2)}


@api.get("/admin/payouts")
async def admin_payouts(status: str = "", user: dict = Depends(require_perm("payouts:view"))):
    flt = {"status": status} if status else {}
    docs = await db.payouts.find(flt).sort([("created_at", -1)]).limit(500).to_list(500)
    partners = await load_many(db.users, [d.get("partner_id", "") for d in docs],
                               {"full_name": 1, "org_name": 1, "email": 1})
    out = []
    for d in docs:
        p = clean(d)
        partner = partners.get(p["partner_id"])
        p["partner"] = clean(partner) if partner else None
        out.append(p)
    rates = await fx_rates()

    def base(row: dict) -> float:
        return float(row.get("net") or 0) / (rates.get((row.get("currency") or BASE_CURRENCY).upper()) or 1.0)

    return {"items": out, "currency": BASE_CURRENCY,
            "totals": {"pending": round(sum(base(p) for p in out if p["status"] == "pending"), 2),
                       "paid": round(sum(base(p) for p in out if p["status"] == "paid"), 2)}}


@api.post("/admin/payouts/{pid}/pay")
async def pay_payout(pid: str, body: dict, user: dict = Depends(require_perm("payouts:pay"))):
    payout = await db.payouts.find_one({"_id": ObjectId(pid)})
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout["status"] == "paid":
        raise HTTPException(status_code=400, detail="This payout is already settled.")
    vendor = await db.vendor_profiles.find_one({"user_id": payout.get("partner_id", "")},
                                              {"payout_hold": 1, "payout_hold_reason": 1})
    if vendor and vendor.get("payout_hold"):
        raise HTTPException(status_code=400,
                            detail=f"Payouts are on hold for this vendor: "
                                   f"{vendor.get('payout_hold_reason') or 'bank verification pending'}.")
    ref = body.get("reference") or "UTR" + uuid.uuid4().hex[:10].upper()
    await db.payouts.update_one({"_id": payout["_id"]},
                                {"$set": {"status": "paid", "reference": ref, "paid_at": iso(now_utc())}})
    await audit(user, "payout.pay", "payout", pid, {"net": payout["net"], "reference": ref})
    await notify(payout["partner_id"], "Payout settled",
                 f"{fmt_money(payout['net'])} for {payout['event_title']} has been transferred. Reference {ref}.",
                 "order", "/partner")
    return {"status": "paid", "reference": ref}


@api.post("/admin/payouts/generate")
async def run_payout_generation(user: dict = Depends(require_perm("payouts:pay"))):
    created = await generate_payouts()
    await audit(user, "payout.generate", "payout", "", {"created": created})
    return {"created": created}


@api.get("/")
async def root():
    return {"service": "Buddilio API", "status": "ok"}


@app.websocket("/api/ws")
async def ws_chat(websocket: WebSocket, token: str = Query("")):
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
        uid = payload["sub"]
    except Exception:
        await websocket.accept()
        await websocket.close(code=4401)
        return
    await hub.connect(uid, websocket)
    convs = await db.conversations.find({"members": uid}, {"members": 1}).limit(200).to_list(200)
    peers = {m for c in convs for m in c["members"] if m != uid}
    await hub.send_to(peers, {"type": "presence", "user_id": uid, "online": True})
    await websocket.send_json({"type": "ready", "online": hub.online_among(peers)})
    try:
        while True:
            data = await websocket.receive_json()
            kind = data.get("type")
            cid = data.get("conversation_id")
            if kind in ("typing", "stop_typing") and cid:
                conv = await db.conversations.find_one({"_id": ObjectId(cid)})
                if conv and uid in conv["members"]:
                    await hub.send_to([m for m in conv["members"] if m != uid],
                                      {"type": kind, "conversation_id": cid, "user_id": uid})
            elif kind == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.info(f"ws closed: {e}")
    finally:
        await hub.disconnect(uid, websocket)
        if not hub.is_online(uid):
            await hub.send_to(peers, {"type": "presence", "user_id": uid, "online": False})


async def payout_loop():
    while True:
        try:
            n = await generate_payouts()
            if n:
                logger.info(f"generated {n} partner payouts")
        except Exception as e:
            logger.error(f"payout loop error: {e}")
        await asyncio.sleep(3600)


async def reminder_loop():
    """Sends a one-time email + in-app reminder ~24h before each event starts."""
    while True:
        try:
            window_end = iso(now_utc() + timedelta(hours=24))
            events = await db.events.find({"status": "published", "starts_at": {"$gte": iso(now_utc()), "$lte": window_end}}).limit(200).to_list(200)
            for ev in events:
                eid = str(ev["_id"])
                parts = await db.event_participants.find({"event_id": eid, "status": "confirmed"}).limit(500).to_list(500)
                starts = datetime.fromisoformat(ev["starts_at"])
                due = [p for p in parts if not p.get("reminded")]
                people = await load_many(db.users, [p["user_id"] for p in due],
                                         {"email": 1, "full_name": 1, "notification_prefs": 1})
                for p in due:
                    await db.event_participants.update_one({"_id": p["_id"]}, {"$set": {"reminded": True}})
                    await notify(p["user_id"], "Event reminder",
                                 f"{ev['title']} starts {starts.strftime('%a %d %b at %I:%M %p')} — {ev.get('venue','')}, {ev['city']}.",
                                 "reminder", f"/events/{eid}", email=False)
                    u = people.get(p["user_id"])
                    if u and (u.get("notification_prefs") or {}).get("email", True):
                        await send_tpl("event_reminder", u["email"], {
                            "first_name": first_name(u.get("full_name")), "event_title": ev["title"],
                            "when": starts.strftime("%a %d %b, %I:%M %p"), "venue": ev.get("venue", ""),
                            "city": ev["city"], "host": ev.get("partner_name", "Buddilio"),
                            "event_url": f"{FRONTEND_URL}/events/{eid}"})
        except Exception as e:
            logger.error(f"reminder loop error: {e}")
        await asyncio.sleep(3600)


# ---------------- Buddy AI concierge ----------------
class AiChatIn(BaseModel):
    session_id: str
    message: str


async def ai_event_rows(user: dict) -> List[dict]:
    """The only events Buddy is allowed to recommend: upcoming published ones, member's city first."""
    fields = {"title": 1, "city": 1, "category": 1, "starts_at": 1, "venue": 1,
              "price": 1, "price_input": 1, "price_currency": 1}
    q = {"status": "published", "starts_at": {"$gte": iso(now_utc())}}
    near = []
    if user.get("city"):
        near = await db.events.find({**q, "city": user["city"]}, fields) \
            .sort("starts_at", 1).limit(20).to_list(20)
    rest = await db.events.find(q, fields).sort("starts_at", 1).limit(40).to_list(40)
    rows, seen = [], set()
    for e in near + rest:
        eid = str(e["_id"])
        if eid in seen:
            continue
        seen.add(eid)
        cur = (e.get("price_currency") or BASE_CURRENCY).upper()
        amt = e.get("price_input") if e.get("price_input") not in (None, "") else e.get("price", 0)
        try:
            when = datetime.fromisoformat(e["starts_at"].replace("Z", "+00:00")).strftime("%a %d %b, %I:%M %p")
        except Exception:
            when = (e.get("starts_at") or "")[:16]
        rows.append({"id": eid, "title": e.get("title", ""), "city": e.get("city", ""),
                     "category": e.get("category", ""), "when": when,
                     "price_label": "Free" if not amt else f"{cur} {float(amt):,.0f}"})
    return rows[:45]


async def ai_system_prompt(user: dict) -> str:
    rows = await ai_event_rows(user)
    plan = await membership_active(user["id"])
    credit = await credit_balance(user["id"])
    extras = {
        "membership": (plan or {}).get("plan_name", ""),
        "credit": f"{BASE_CURRENCY} {credit:,.0f}" if credit else "",
        "today": now_utc().strftime("%A %d %B %Y"),
        "help": await ai_help_block(),
    }
    return ai.system_prompt(user, ai.event_lines(rows), extras)


async def ai_used_today(user_id: str) -> int:
    since = iso(now_utc() - timedelta(days=1))
    return await db.ai_messages.count_documents(
        {"user_id": user_id, "role": "user", "created_at": {"$gte": since}})


_HELP_CACHE = {"at": None, "text": ""}
HELP_SLUGS = ["faq", "refund", "guidelines", "safety", "about"]


async def ai_help_block() -> str:
    """CMS policy pages, cached 10 minutes, so Buddy can settle support questions on its own."""
    if _HELP_CACHE["at"] and (now_utc() - _HELP_CACHE["at"]).total_seconds() < 600:
        return _HELP_CACHE["text"]
    docs = await db.cms_pages.find({"slug": {"$in": HELP_SLUGS}}, {"slug": 1, "title": 1, "content": 1}) \
        .limit(len(HELP_SLUGS)).to_list(len(HELP_SLUGS))
    order = {s: i for i, s in enumerate(HELP_SLUGS)}
    docs.sort(key=lambda d: order.get(d.get("slug"), 99))
    text = "\n\n".join(f"{d.get('title', d['slug'])} (/p/{d['slug']}):\n{(d.get('content') or '').strip()[:900]}"
                       for d in docs if (d.get("content") or "").strip())
    _HELP_CACHE.update({"at": now_utc(), "text": text})
    return text


@api.get("/ai/config")
async def ai_config(user: dict = Depends(get_current_user)):
    return {"enabled": ai.ai_enabled(), "model": ai.AI_MODEL,
            "suggestions": ai.starter_prompts(user.get("city", "")),
            "used_today": await ai_used_today(user["id"]), "daily_cap": ai.DAILY_MESSAGE_CAP}


@api.get("/ai/guest/config")
async def ai_guest_config():
    return {"enabled": ai.ai_enabled(), "suggestions": ai.GUEST_PROMPTS}


@api.get("/ai/history")
async def ai_history(session_id: str, user: dict = Depends(get_current_user)):
    docs = await db.ai_messages.find({"user_id": user["id"], "session_id": session_id},
                                     {"role": 1, "content": 1, "created_at": 1}) \
        .sort("created_at", 1).limit(200).to_list(200)
    # hide user turns whose stream was abandoned — they never got a reply
    out = [{"role": d["role"], "content": d["content"], "created_at": d["created_at"]}
           for i, d in enumerate(docs)
           if d["role"] != "user" or (i + 1 < len(docs) and docs[i + 1]["role"] == "assistant")]
    return {"messages": out}


@api.post("/ai/concierge")
async def ai_concierge(payload: AiChatIn, user: dict = Depends(get_current_user)):
    """Streams Buddy's reply as SSE. Conversation history lives in db.ai_messages, keyed by session."""
    if not ai.ai_enabled():
        raise HTTPException(status_code=503, detail="Buddy AI isn't switched on yet.")
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Type a message first.")
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="Please keep your message under 1000 characters.")
    if await ai_used_today(user["id"]) >= ai.DAILY_MESSAGE_CAP:
        raise HTTPException(status_code=429,
                            detail="You've used up today's Buddy AI questions. They reset in 24 hours.")

    prior = await db.ai_messages.find({"user_id": user["id"], "session_id": payload.session_id},
                                      {"role": 1, "content": 1}) \
        .sort("created_at", 1).limit(40).to_list(40)
    # keep only completed turns — a user message whose stream was abandoned has no assistant reply
    history = []
    for i, p in enumerate(prior):
        if p["role"] == "user" and (i + 1 >= len(prior) or prior[i + 1]["role"] != "assistant"):
            continue
        history.append({"role": p["role"], "content": p["content"]})
    system = await ai_system_prompt(user)
    await db.ai_messages.insert_one({"user_id": user["id"], "session_id": payload.session_id,
                                     "role": "user", "content": text, "created_at": iso(now_utc())})

    async def gen():
        parts = []
        try:
            async for delta in ai.stream_reply(payload.session_id, system, history, text):
                parts.append(delta)
                yield f"data: {json.dumps({'delta': delta})}\n\n"
        except Exception as e:
            logger.error(f"Buddy AI stream failed: {e}")
            yield f"data: {json.dumps({'error': 'Buddy could not answer that one. Please try again.'})}\n\n"
        reply = "".join(parts).strip()
        if reply:
            await db.ai_messages.insert_one({"user_id": user["id"], "session_id": payload.session_id,
                                             "role": "assistant", "content": reply,
                                             "created_at": iso(now_utc())})
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})


AI_PICKS_TTL_HOURS = 6


async def ai_hydrate_picks(picks: List[dict]) -> List[dict]:
    """Turn cached/fresh {id, why} rows into full event cards, dropping anything no longer bookable."""
    ids = []
    for p in picks:
        try:
            ids.append(ObjectId(p["id"]))
        except Exception:
            continue
    if not ids:
        return []
    docs = await db.events.find({"_id": {"$in": ids}, "status": "published",
                                 "starts_at": {"$gte": iso(now_utc())}}).limit(len(ids)).to_list(len(ids))
    by_id = {str(d["_id"]): d for d in docs}
    out = []
    for p in picks:
        doc = by_id.get(p["id"])
        if doc:
            item = clean(doc)
            item["why"] = p["why"]
            out.append(item)
    return out


@api.get("/ai/picks")
async def ai_picks(refresh: int = 0, user: dict = Depends(get_current_user)):
    """Three AI-chosen events for this member, each with a one-line reason. Cached 6h per member."""
    if not ai.ai_enabled():
        return {"enabled": False, "items": []}
    cached = await db.ai_picks.find_one({"user_id": user["id"]})
    if cached:
        age = (now_utc() - datetime.fromisoformat(cached["created_at"])).total_seconds()
        # one refresh a minute per member — the Refresh button shouldn't be able to burn the LLM balance
        fresh = age < AI_PICKS_TTL_HOURS * 3600 if not refresh else age < 60
        if fresh:
            items = await ai_hydrate_picks(cached.get("picks", []))
            if items:
                return {"enabled": True, "items": items, "generated_at": cached["created_at"]}

    joined = [p["event_id"] for p in await db.event_participants.find(
        {"user_id": user["id"]}, {"event_id": 1}).limit(200).to_list(200)]
    rows = [r for r in await ai_event_rows(user) if r["id"] not in joined][:12]
    if not rows:
        return {"enabled": True, "items": []}

    u = await db.users.find_one({"_id": ObjectId(user["id"])})
    plan = await membership_active(user["id"])
    member_block = "\n".join([
        f"- City: {u.get('city') or 'not set'} ({u.get('country') or 'unknown country'})",
        f"- Interests: {', '.join(u.get('interests') or []) or 'none given'}",
        f"- Preferred categories: {', '.join(u.get('event_categories') or []) or 'none given'}",
        f"- Lifestyle: {', '.join(u.get('lifestyle') or []) or 'none given'}",
        f"- Membership: {(plan or {}).get('plan_name', 'none')}",
        f"- Events booked so far: {len(joined)}",
    ])
    picks = await ai.pick_events(f"picks-{user['id']}", member_block, ai.event_lines(rows))
    valid_ids = {r["id"] for r in rows}
    picks = [p for p in picks if p["id"] in valid_ids][:3]
    if not picks:
        return {"enabled": True, "items": []}
    ts = iso(now_utc())
    await db.ai_picks.update_one({"user_id": user["id"]},
                                 {"$set": {"picks": picks, "created_at": ts}}, upsert=True)
    return {"enabled": True, "items": await ai_hydrate_picks(picks), "generated_at": ts}


AI_MATCH_TTL_HOURS = 6


@api.get("/events/{event_id}/ai-companions")
async def ai_companions(event_id: str, refresh: int = 0, user: dict = Depends(get_current_user)):
    """Up to 3 members worth messaging about this event, each with a reason. Cached 6h per member+event."""
    if not ai.ai_enabled():
        return {"enabled": False, "items": []}
    try:
        ev = await db.events.find_one({"_id": ObjectId(event_id), "status": "published"})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event id")
    if not ev:
        return {"enabled": True, "items": []}

    me = await db.users.find_one({"_id": ObjectId(user["id"])})
    blocked = me.get("blocked", [])

    async def hydrate(matches: List[dict], going: set) -> List[dict]:
        ids = []
        for m in matches:
            try:
                ids.append(ObjectId(m["id"]))
            except Exception:
                continue
        if not ids:
            return []
        docs = await db.users.find({"_id": {"$in": ids}, "status": "active",
                                   "privacy.profile_visibility": {"$ne": "private"}},
                                  PUBLIC_FIELDS).limit(len(ids)).to_list(len(ids))
        by_id = {str(d["_id"]): clean(d) for d in docs}
        out = []
        for m in matches:
            person = by_id.get(m["id"])
            if person and m["id"] not in blocked:
                person["why"] = m["why"]
                person["going"] = m["id"] in going
                out.append(person)
        return out

    parts = await db.event_participants.find({"event_id": event_id, "status": "confirmed"},
                                            {"user_id": 1}).limit(200).to_list(200)
    going = {p["user_id"] for p in parts if p["user_id"] != user["id"]}

    cached = await db.ai_matches.find_one({"user_id": user["id"], "event_id": event_id})
    if cached:
        age = (now_utc() - datetime.fromisoformat(cached["created_at"])).total_seconds()
        if age < (60 if refresh else AI_MATCH_TTL_HOURS * 3600):
            items = await hydrate(cached.get("matches", []), going)
            if items:
                return {"enabled": True, "items": items, "generated_at": cached["created_at"]}

    exclude = [ObjectId(b) for b in blocked if len(b) == 24] + [ObjectId(user["id"])]
    if ev.get("partner_id"):
        try:
            exclude.append(ObjectId(ev["partner_id"]))
        except Exception:
            pass
    base = {"role": "user", "status": "active", "_id": {"$nin": exclude},
            "privacy.profile_visibility": {"$ne": "private"}}
    attendees = await db.users.find({**base, "_id": {"$in": [ObjectId(g) for g in going if len(g) == 24],
                                                    "$nin": exclude}}, PUBLIC_FIELDS).limit(10).to_list(10)
    pool = list(attendees)
    if len(pool) < 10:
        overlap = {"$or": [{"interests": {"$in": me.get("interests") or ["__none__"]}},
                           {"event_categories": ev.get("category")}]}
        nearby = await db.users.find({**base, "city": ev.get("city"), **overlap}, PUBLIC_FIELDS) \
            .limit(12).to_list(12)
        have = {str(p["_id"]) for p in pool}
        pool += [n for n in nearby if str(n["_id"]) not in have][:12 - len(pool)]
    if not pool:
        return {"enabled": True, "items": []}

    lines = []
    for p in pool[:12]:
        pid = str(p["_id"])
        name = (p.get("full_name") or "Member").split(" ")[0]
        lines.append(f"- {name} | {p.get('age') or '?'} | {p.get('city', '')} | "
                     f"{'already going' if pid in going else 'not going yet'} | "
                     f"{', '.join((p.get('interests') or [])[:6]) or 'no interests listed'} | id={pid}")
    member_block = "\n".join([
        f"- City: {me.get('city') or 'not set'}",
        f"- Interests: {', '.join(me.get('interests') or []) or 'none given'}",
        f"- Preferred categories: {', '.join(me.get('event_categories') or []) or 'none given'}",
    ])
    event_block = (f"{ev.get('title')} | {ev.get('category')} | {ev.get('city')} | "
                   f"{(ev.get('starts_at') or '')[:16]} | {ev.get('venue', '')}")
    matches = await ai.match_companions(f"match-{user['id']}-{event_id}", member_block, event_block,
                                        "\n".join(lines))
    valid = {str(p["_id"]) for p in pool}
    matches = [m for m in matches if m["id"] in valid][:3]
    if not matches:
        return {"enabled": True, "items": []}
    ts = iso(now_utc())
    await db.ai_matches.update_one({"user_id": user["id"], "event_id": event_id},
                                   {"$set": {"matches": matches, "created_at": ts}}, upsert=True)
    return {"enabled": True, "items": await hydrate(matches, going), "generated_at": ts}


class InviteIn(BaseModel):
    email: str = ""
    org_name: str = ""
    city: str = ""
    note: str = ""


class InviteAcceptIn(BaseModel):
    full_name: str
    org_name: str
    city: str
    password: str
    mobile: str = ""
    bio: str = ""
    photo: str = ""


class DocumentsIn(BaseModel):
    documents: List[dict] = []


INVITE_DAYS = 14


def invite_public(inv: dict) -> dict:
    out = {"id": str(inv["_id"]), "email": inv.get("email", ""), "org_name": inv.get("org_name", ""),
           "city": inv.get("city", ""), "note": inv.get("note", ""), "status": inv.get("status", "pending"),
           "manager_name": inv.get("manager_name", ""), "created_at": inv.get("created_at", ""),
           "expires_at": inv.get("expires_at", ""), "accepted_by": inv.get("accepted_by", "")}
    if out["status"] == "pending":  # a used or revoked token is never handed back out
        out["link"] = f"{FRONTEND_URL}/vendor-signup?token={inv['token']}"
    return out


@api.post("/console/invites")
async def console_create_invite(payload: InviteIn, user: dict = Depends(require_perm("invites:manage", active=True))):
    """A signup link the vendor fills in themselves — details, photo and documents included."""
    email = payload.email.lower().strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}", email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address for the vendor.")
    if email and await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Someone already has an account with that email.")
    doc = {"token": secrets.token_urlsafe(32), "manager_id": user["id"], "manager_name": user["full_name"],
           "email": email, "org_name": payload.org_name.strip(), "city": payload.city.strip(),
           "note": payload.note.strip()[:400], "status": "pending", "accepted_by": "",
           "created_at": iso(now_utc()), "expires_at": iso(now_utc() + timedelta(days=INVITE_DAYS))}
    res = await db.vendor_invites.insert_one(doc)
    inv = await db.vendor_invites.find_one({"_id": res.inserted_id})
    if email:
        try:
            await send_tpl("vendor_invite", email, {
                "inviter": user["full_name"], "org_name": payload.org_name or "you",
                "note": payload.note or "", "invite_days": INVITE_DAYS,
                "invite_url": invite_public(inv)["link"]})
        except Exception as e:
            logger.error(f"vendor invite email failed: {e}")
    await audit(user, "vendor.invite", "invite", str(res.inserted_id), {"email": email})
    return invite_public(inv)


@api.get("/console/invites")
async def console_invites(user: dict = Depends(require_perm("invites:manage"))):
    q = {} if user["role"] == "admin" else {"manager_id": user["id"]}
    docs = await db.vendor_invites.find(q).sort("created_at", -1).limit(100).to_list(100)
    return {"items": [invite_public(d) for d in docs]}


@api.delete("/console/invites/{iid}")
async def console_revoke_invite(iid: str, user: dict = Depends(require_perm("invites:manage", active=True))):
    q = {"_id": ObjectId(iid)} if user["role"] == "admin" else {"_id": ObjectId(iid), "manager_id": user["id"]}
    inv = await db.vendor_invites.find_one(q)
    if not inv:
        raise HTTPException(status_code=404, detail="Invite not found")
    if inv.get("status") == "accepted":
        raise HTTPException(status_code=400, detail="That invite has already been used.")
    await db.vendor_invites.update_one({"_id": inv["_id"]}, {"$set": {"status": "revoked"}})
    await audit(user, "vendor.invite_revoke", "invite", iid)
    return {"ok": True}


async def live_invite(token: str) -> dict:
    inv = await db.vendor_invites.find_one({"token": token, "status": "pending"})
    if not inv or datetime.fromisoformat(inv["expires_at"]) < now_utc():
        raise HTTPException(status_code=404, detail="This invite link is no longer valid.")
    return inv


@api.get("/vendor-invite/{token}")
async def get_vendor_invite(token: str):
    inv = await live_invite(token)
    return {"email": inv.get("email", ""), "org_name": inv.get("org_name", ""), "city": inv.get("city", ""),
            "note": inv.get("note", ""), "manager_name": inv.get("manager_name", ""),
            "expires_at": inv["expires_at"]}


@api.post("/vendor-invite/{token}/accept")
async def accept_vendor_invite(token: str, payload: InviteAcceptIn, response: Response):
    inv = await live_invite(token)
    email = (inv.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="This invite has no email attached. Ask for a new link.")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Use at least 8 characters for your password.")
    if not payload.org_name.strip() or not payload.city.strip():
        raise HTTPException(status_code=400, detail="Organisation and city are both required.")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    c = country_for_city(payload.city) or {}
    doc = {"full_name": payload.full_name.strip()[:120], "email": email,
           "mobile": payload.mobile.strip()[:24],
           "password_hash": hash_password(payload.password), "role": "partner", "status": "active",
           "org_name": payload.org_name.strip(), "city": payload.city.strip(),
           "country": c.get("name", ""), "country_code": c.get("code", ""),
           "bio": safe_html(payload.bio or "")[:4000], "photo": payload.photo, "verified": False, "email_verified": True,
           "documents": [], "managed_by": inv["manager_id"], "created_by_name": inv.get("manager_name", ""),
           "privacy": {"profile_visibility": "public", "who_can_message": "everyone"},
           "notification_prefs": {"email": True, "in_app": True, "sms": False, "push": True},
           "blocked": [], "connections": [], "saved_events": [], "created_at": iso(now_utc())}
    res = await db.users.insert_one(doc)
    vid = str(res.inserted_id)
    await db.vendor_invites.update_one({"_id": inv["_id"]},
                                       {"$set": {"status": "accepted", "accepted_by": vid,
                                                 "accepted_at": iso(now_utc())}})
    await notify(inv["manager_id"], "Vendor signed up",
                 f"{payload.org_name} completed their organiser signup.", "vendor", "/console")
    token_jwt = create_access_token(vid, email, "partner")
    set_cookies(response, token_jwt)
    return {"access_token": token_jwt, "user": clean(await db.users.find_one({"_id": res.inserted_id}))}


@api.put("/partner/documents")
async def partner_documents(payload: DocumentsIn, user: dict = Depends(partner_only)):
    """Vendors attach licences, insurance or ID scans to their own account."""
    docs = []
    if len(payload.documents) > 10:
        raise HTTPException(status_code=400, detail="You can keep up to 10 documents on file.")
    for d in payload.documents:
        url, name = str(d.get("url", "")), str(d.get("name", "Document"))[:120]
        if not url.startswith("/api/files/"):
            raise HTTPException(status_code=400, detail="Upload documents through Buddilio first.")
        docs.append({"name": name, "url": url, "kind": str(d.get("kind", ""))[:40],
                     "uploaded_at": iso(now_utc())})
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"documents": docs}})
    return {"ok": True, "documents": docs}


@api.get("/console/payouts")
async def console_payouts(user: dict = Depends(require_perm("payouts:view"))):
    """What each managed vendor has earned, and what's still owed."""
    q = {"role": "partner"} if user["role"] == "admin" else {"role": "partner", "managed_by": user["id"]}
    vendors = await db.users.find(q, {"org_name": 1, "full_name": 1}).limit(500).to_list(500)
    names = {str(v["_id"]): v.get("org_name") or v.get("full_name") for v in vendors}
    if not names:
        return {"items": [], "totals": {"paid": 0, "pending": 0, "gross": 0, "fees": 0, "currency": BASE_CURRENCY}}
    rows = await db.payouts.find({"partner_id": {"$in": list(names)}}) \
        .sort("created_at", -1).limit(500).to_list(500)
    items, paid, pending, gross, fees = [], 0.0, 0.0, 0.0, 0.0
    for r in rows:
        net = float(r.get("net") or 0)
        gross += float(r.get("gross") or 0)
        fees += float(r.get("fee") or 0)
        if r.get("status") == "paid":
            paid += net
        else:
            pending += net
        items.append({"id": str(r["_id"]), "vendor": names.get(r["partner_id"], "—"),
                      "vendor_id": r["partner_id"], "event_title": r.get("event_title", ""),
                      "orders": r.get("orders", 0), "gross": float(r.get("gross") or 0),
                      "fee": float(r.get("fee") or 0), "fee_percent": r.get("fee_percent", 0),
                      "net": net, "currency": r.get("currency", BASE_CURRENCY),
                      "status": r.get("status", "pending"), "reference": r.get("reference", ""),
                      "created_at": r.get("created_at", ""), "paid_at": r.get("paid_at", "")})
    return {"items": items, "totals": {"paid": round(paid, 2), "pending": round(pending, 2),
                                       "gross": round(gross, 2), "fees": round(fees, 2),
                                       "currency": BASE_CURRENCY}}


@api.get("/admin/vendor-activity")
async def admin_vendor_activity(user: dict = Depends(require_perm("audit:view"))):
    """Who created, edited, suspended or invited which vendor, and when."""
    rows = await db.audit_logs.find({"action": {"$regex": "^(vendor|manager)\\."}}) \
        .sort("created_at", -1).limit(200).to_list(200)
    actor_ids, vendor_ids = set(), set()
    for r in rows:
        actor_ids.add(r.get("actor_id", ""))
        if r.get("entity") == "user" and r.get("entity_id"):
            vendor_ids.add(r["entity_id"])
    people = {}
    ids = [ObjectId(i) for i in (actor_ids | vendor_ids) if i and len(i) == 24]
    if ids:
        for u in await db.users.find({"_id": {"$in": ids}},
                                     {"full_name": 1, "org_name": 1, "role": 1}).limit(400).to_list(400):
            people[str(u["_id"])] = {"name": u.get("org_name") or u.get("full_name", ""), "role": u.get("role", "")}
    items = []
    for r in rows:
        actor = people.get(r.get("actor_id", ""), {})
        target = people.get(r.get("entity_id", ""), {})
        items.append({"id": str(r["_id"]), "action": r["action"],
                      "actor": actor.get("name") or r.get("actor_email", "—"),
                      "actor_role": actor.get("role", ""), "actor_email": r.get("actor_email", ""),
                      "target": target.get("name", ""), "target_id": r.get("entity_id", ""),
                      "entity": r.get("entity", ""), "meta": r.get("meta", {}),
                      "created_at": r.get("created_at", "")})
    return {"items": items}


AI_COPY_CAP = 20


@api.post("/partner/ai-draft")
async def partner_ai_draft(body: dict, user: dict = Depends(partner_only)):
    """Turns an organiser's bullet notes into a title, description, rules and highlights."""
    if not ai.ai_enabled():
        raise HTTPException(status_code=503, detail="Buddy AI isn't switched on yet.")
    notes = str(body.get("notes", "")).strip()
    if len(notes) < 15:
        raise HTTPException(status_code=400, detail="Give Buddy a few more details to work with.")
    if len(notes) > 1500:
        raise HTTPException(status_code=400, detail="Please keep your notes under 1500 characters.")
    since = iso(now_utc() - timedelta(days=1))
    recent = await db.ai_drafts.find_one({"user_id": user["id"], "notes": notes[:500],
                                          "created_at": {"$gte": iso(now_utc() - timedelta(minutes=5))}})
    if recent:  # same notes twice in a row shouldn't cost another draft
        return {**recent["draft"],
                "used_today": await db.ai_drafts.count_documents(
                    {"user_id": user["id"], "created_at": {"$gte": since}}),
                "daily_cap": AI_COPY_CAP}
    used = await db.ai_drafts.count_documents({"user_id": user["id"], "created_at": {"$gte": since}})
    if used >= AI_COPY_CAP:
        raise HTTPException(status_code=429, detail="You've used today's AI drafts. They reset in 24 hours.")
    brief = "\n".join(filter(None, [
        f"Category: {body.get('category', '')}", f"City: {body.get('city', '')}",
        f"Venue: {body.get('venue', '')}", f"Starts: {str(body.get('starts_at', ''))[:16]}",
        f"Price: {body.get('price', '')} {body.get('price_currency', '')}",
        f"Capacity: {body.get('capacity', '')}", f"Notes: {notes}"]))
    draft = await ai.draft_event_copy(f"copy-{user['id']}-{secrets.token_hex(4)}", brief)
    if not draft.get("title"):
        raise HTTPException(status_code=502, detail="Buddy couldn't draft that. Try adding a bit more detail.")
    await db.ai_drafts.insert_one({"user_id": user["id"], "notes": notes[:500], "draft": draft,
                                   "created_at": iso(now_utc())})
    return {**draft, "used_today": used + 1, "daily_cap": AI_COPY_CAP}


class AiGuestIn(BaseModel):
    message: str
    session_id: str = ""


GUEST_AI_IP_CAP = 25  # rolling 24h abuse guard; the UI itself allows one free question per visitor


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() or (request.client.host if request.client else "") or "unknown")


@api.post("/ai/guest")
async def ai_guest(payload: AiGuestIn, request: Request):
    """One-shot Buddy answer for visitors who haven't joined yet. No history, no account needed."""
    if not ai.ai_enabled():
        raise HTTPException(status_code=503, detail="Buddy AI isn't switched on yet.")
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Type a question first.")
    if len(text) > 500:
        raise HTTPException(status_code=400, detail="Please keep your question under 500 characters.")
    ip = client_ip(request)
    since = iso(now_utc() - timedelta(days=1))
    if await db.ai_guest_asks.count_documents({"ip": ip, "created_at": {"$gte": since}}) >= GUEST_AI_IP_CAP:
        raise HTTPException(status_code=429,
                            detail="Buddy has answered a lot of questions from here today. "
                                   "Join free and keep chatting inside Buddilio.")
    rows = await ai_event_rows({})
    system = ai.guest_system_prompt(ai.event_lines(rows), {
        "today": now_utc().strftime("%A %d %B %Y"),
        "cities": sum(len(c.get("cities", [])) for c in COUNTRIES), "countries": len(COUNTRIES),
        "help": await ai_help_block(),
    })

    async def gen():
        parts = []
        try:
            async for delta in ai.stream_reply(payload.session_id or f"guest-{secrets.token_hex(6)}",
                                               system, [], text):
                parts.append(delta)
                yield f"data: {json.dumps({'delta': delta})}\n\n"
        except Exception as e:
            logger.error(f"Buddy AI guest stream failed: {e}")
            yield f"data: {json.dumps({'error': 'Buddy could not answer that one. Please try again.'})}\n\n"
        reply = "".join(parts).strip()
        await db.ai_guest_asks.insert_one({"ip": ip, "question": text, "reply": reply,
                                           "created_at": iso(now_utc())})
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})


# ---------------- vendor management console ----------------
class ManagerRegisterIn(BaseModel):
    full_name: str
    email: str
    password: str
    org_name: str = ""
    mobile: str = ""
    country: str = ""


class VendorIn(BaseModel):
    full_name: str
    email: str
    org_name: str
    city: str
    mobile: str = ""
    country: str = ""
    bio: str = ""
    photo: str = ""


class VendorPatch(BaseModel):
    full_name: str = ""
    org_name: str = ""
    city: str = ""
    mobile: str = ""
    bio: str = ""
    photo: str = ""
    status: str = ""
    verified: Optional[bool] = None


VENDOR_FIELDS = {"full_name": 1, "email": 1, "org_name": 1, "city": 1, "country": 1, "mobile": 1,
                 "status": 1, "verified": 1, "photo": 1, "bio": 1, "rating": 1, "created_at": 1,
                 "managed_by": 1, "documents": 1}


async def vendor_invite(vendor: dict, manager_name: str) -> None:
    token = secrets.token_urlsafe(32)
    await db.password_reset_tokens.insert_one({"token": token, "user_id": str(vendor["_id"]),
                                               "used": False, "expires_at": now_utc() + timedelta(days=7)})
    await send_tpl("vendor_created", vendor["email"], {
        "first_name": first_name(vendor.get("full_name")), "manager_name": manager_name,
        "org_name": vendor.get("org_name") or vendor.get("full_name"),
        "reset_url": f"{FRONTEND_URL}/reset-password?token={token}"})


async def vendor_stats(ids: List[str]) -> dict:
    """Events, published count and seats sold per vendor, in two queries."""
    out = {v: {"events": 0, "published": 0, "participants": 0} for v in ids}
    if not ids:
        return out
    events = await db.events.find({"partner_id": {"$in": ids}},
                                  {"partner_id": 1, "status": 1}).limit(2000).to_list(2000)
    by_event = {str(e["_id"]): e["partner_id"] for e in events}
    for e in events:
        row = out.setdefault(e["partner_id"], {"events": 0, "published": 0, "participants": 0})
        row["events"] += 1
        if e.get("status") == "published":
            row["published"] += 1
    if by_event:
        parts = await db.event_participants.find({"event_id": {"$in": list(by_event)}, "status": "confirmed"},
                                                {"event_id": 1}).limit(5000).to_list(5000)
        for p in parts:
            pid = by_event.get(p["event_id"])
            if pid in out:
                out[pid]["participants"] += 1
    return out


@api.post("/console/register")
async def console_register(payload: ManagerRegisterIn, response: Response):
    """Anyone can request a console account; it stays pending until an admin approves it."""
    email = payload.email.lower().strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}", email):
        raise HTTPException(status_code=400, detail="Please enter a valid work email address.")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Use at least 8 characters for your password.")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    doc = {"full_name": payload.full_name.strip(), "email": email, "mobile": payload.mobile.strip(),
           "password_hash": hash_password(payload.password), "role": "manager", "status": "pending",
           "org_name": payload.org_name.strip(), "country": payload.country, "city": "",
           "photo": "", "bio": "", "verified": False, "email_verified": False,
           "notification_prefs": {"email": True, "in_app": True, "sms": False, "push": False},
           "blocked": [], "connections": [], "saved_events": [], "created_at": iso(now_utc())}
    res = await db.users.insert_one(doc)
    mid = str(res.inserted_id)
    for a in await db.users.find({"role": "admin"}, {"_id": 1}).limit(10).to_list(10):
        await notify(str(a["_id"]), "New console account request",
                     f"{payload.full_name} ({email}) wants vendor management access.",
                     "console", "/admin", email=False)
    await send_tpl("console_requested", email, {"first_name": first_name(payload.full_name),
                                               "console_url": f"{FRONTEND_URL}/console"})
    token = create_access_token(mid, email, "manager")
    set_cookies(response, token)
    return {"access_token": token, "user": clean(await db.users.find_one({"_id": res.inserted_id}))}


@api.get("/console/summary")
async def console_summary(user: dict = Depends(require_perm("vendors:view"))):
    q = {"role": "partner"} if user["role"] == "admin" else {"role": "partner", "managed_by": user["id"]}
    vendors = await db.users.find(q, {"status": 1}).limit(500).to_list(500)
    ids = [str(v["_id"]) for v in vendors]
    stats = await vendor_stats(ids)
    return {"approved": user["role"] == "admin" or user.get("status") == "active",
            "vendors": len(vendors),
            "active_vendors": sum(1 for v in vendors if v.get("status") == "active"),
            "events": sum(s["events"] for s in stats.values()),
            "published": sum(s["published"] for s in stats.values()),
            "seats_sold": sum(s["participants"] for s in stats.values())}


@api.get("/console/vendors")
async def console_vendors(q: str = "", user: dict = Depends(require_perm("vendors:view"))):
    query = {"role": "partner"} if user["role"] == "admin" else {"role": "partner", "managed_by": user["id"]}
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"full_name": rx}, {"email": rx}, {"org_name": rx}, {"city": rx}]
    docs = await db.users.find(query, VENDOR_FIELDS).sort("created_at", -1).limit(200).to_list(200)
    stats = await vendor_stats([str(d["_id"]) for d in docs])
    items = []
    for d in docs:
        v = clean(d)
        v.update(stats.get(v["id"], {"events": 0, "published": 0, "participants": 0}))
        items.append(v)
    return {"items": items}


async def owned_vendor(vid: str, user: dict) -> dict:
    try:
        doc = await db.users.find_one({"_id": ObjectId(vid), "role": "partner"}, VENDOR_FIELDS)
    except Exception:
        raise HTTPException(status_code=404, detail="Vendor not found")
    if not doc or (user["role"] != "admin" and doc.get("managed_by") != user["id"]):
        raise HTTPException(status_code=404, detail="Vendor not found")
    return doc


@api.get("/console/vendors/{vid}")
async def console_vendor(vid: str, user: dict = Depends(require_perm("vendors:view"))):
    doc = await owned_vendor(vid, user)
    v = clean(doc)
    v.update((await vendor_stats([vid])).get(vid, {}))
    events = await db.events.find({"partner_id": vid}, {"title": 1, "status": 1, "city": 1, "starts_at": 1}) \
        .sort("starts_at", -1).limit(20).to_list(20)
    v["recent_events"] = [clean(e) for e in events]
    return v


@api.post("/console/vendors")
async def console_create_vendor(payload: VendorIn, user: dict = Depends(require_perm("vendors:manage", active=True))):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    if not payload.org_name.strip() or not payload.full_name.strip():
        raise HTTPException(status_code=400, detail="Vendor name and organisation are both required.")
    if not payload.city.strip():
        raise HTTPException(status_code=400, detail="Please choose the vendor's city.")
    c = country_for_city(payload.city) or {}
    doc = {"full_name": payload.full_name.strip(), "email": email, "mobile": payload.mobile.strip(),
           "password_hash": hash_password(secrets.token_urlsafe(24)), "role": "partner", "status": "active",
           "org_name": payload.org_name.strip(), "city": payload.city.strip(),
           "country": payload.country or c.get("name", ""), "country_code": c.get("code", ""),
           "bio": safe_html(payload.bio or "")[:4000], "photo": payload.photo, "verified": False, "email_verified": False,
           "managed_by": user["id"], "created_by_name": user["full_name"],
           "privacy": {"profile_visibility": "public", "who_can_message": "everyone"},
           "notification_prefs": {"email": True, "in_app": True, "sms": False, "push": True},
           "blocked": [], "connections": [], "saved_events": [], "created_at": iso(now_utc())}
    res = await db.users.insert_one(doc)
    vendor = await db.users.find_one({"_id": res.inserted_id})
    try:
        await vendor_invite(vendor, user["full_name"])
    except Exception as e:  # an email hiccup must not lose the vendor account
        logger.error(f"vendor invite email failed: {e}")
    await audit(user, "vendor.create", "user", str(res.inserted_id), {"email": email})
    v = clean({k: vendor.get(k) for k in list(VENDOR_FIELDS) + ["_id"] if k in vendor})
    v.update({"events": 0, "published": 0, "participants": 0})
    return v


@api.patch("/console/vendors/{vid}")
async def console_update_vendor(vid: str, payload: VendorPatch, user: dict = Depends(require_perm("vendors:manage", active=True))):
    await owned_vendor(vid, user)
    upd = {k: v for k, v in payload.dict().items() if k not in ("status", "verified") and v not in ("", None)}
    if payload.status:
        if payload.status not in ("active", "suspended"):
            raise HTTPException(status_code=400, detail="Status must be either active or suspended.")
        upd["status"] = payload.status
    if payload.verified is not None:
        upd["verified"] = payload.verified
    if upd.get("city"):
        c = country_for_city(upd["city"]) or {}
        upd["country"], upd["country_code"] = c.get("name", ""), c.get("code", "")
    if not upd:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    await db.users.update_one({"_id": ObjectId(vid)}, {"$set": upd})
    await audit(user, "vendor.update", "user", vid, upd)
    v = clean(await db.users.find_one({"_id": ObjectId(vid)}, VENDOR_FIELDS))
    v.update((await vendor_stats([vid])).get(vid, {}))
    return v


@api.post("/console/vendors/{vid}/invite")
async def console_resend_invite(vid: str, user: dict = Depends(require_perm("vendors:manage", active=True))):
    doc = await owned_vendor(vid, user)
    await vendor_invite(await db.users.find_one({"_id": doc["_id"]}), user["full_name"])
    return {"ok": True, "message": f"Set-password link sent to {doc['email']}."}


# ---------------- email template editor ----------------
class EmailTplIn(BaseModel):
    subject: str = Field(max_length=200)
    title: str = Field(max_length=200)
    body: str = Field(max_length=20000)
    cta_label: str = Field(default="", max_length=80)
    cta_url: str = Field(default="", max_length=300)


@api.get("/admin/email-templates")
async def list_email_templates(user: dict = Depends(require_perm("content:manage"))):
    saved = {d["key"]: d for d in await db.email_templates.find({}).limit(60).to_list(60)}
    items = []
    for key, base in EMAIL_TEMPLATES.items():
        s = saved.get(key, {})
        items.append({f: (s.get(f) if s.get(f) not in (None, "") else base[f]) for f in TPL_FIELDS} | {
            "key": key, "label": base["label"], "group": base["group"], "vars": base["vars"],
            "customised": key in saved})
    return {"items": items,
            "defaults": {k: {f: v[f] for f in TPL_FIELDS} for k, v in EMAIL_TEMPLATES.items()},
            "groups": sorted({t["group"] for t in EMAIL_TEMPLATES.values()})}


@api.put("/admin/email-templates/{key}")
async def update_email_template(key: str, payload: EmailTplIn,
                                user: dict = Depends(require_perm("content:manage"))):
    if key not in EMAIL_TEMPLATES:
        raise HTTPException(status_code=404, detail="Unknown email.")
    if not payload.subject.strip() or not payload.body.strip():
        raise HTTPException(status_code=400, detail="An email needs a subject and a body.")
    before = await email_template(key)
    doc = payload.model_dump()
    doc["body"] = safe_html(doc["body"])
    doc["title"] = safe_html(doc["title"])
    doc["cta_url"] = doc["cta_url"].strip()
    if doc["cta_url"] and not (doc["cta_url"].startswith("{{") or doc["cta_url"].startswith("https://")
                               or doc["cta_url"].startswith("/") or doc["cta_url"].startswith("mailto:")):
        raise HTTPException(status_code=400, detail="The button link must be a {{variable}}, /path or https://…")
    await db.email_templates.update_one({"key": key},
                                       {"$set": doc | {"updated_at": iso(now_utc())}}, upsert=True)
    await audit(user, "email_template.update", "email_template", key,
                {"old_subject": before["subject"][:120], "new_subject": doc["subject"][:120]})
    return await email_template(key)


@api.delete("/admin/email-templates/{key}")
async def reset_email_template(key: str, user: dict = Depends(require_perm("content:manage"))):
    if key not in EMAIL_TEMPLATES:
        raise HTTPException(status_code=404, detail="Unknown email.")
    await db.email_templates.delete_one({"key": key})
    await audit(user, "email_template.reset", "email_template", key, {})
    return await email_template(key)


@api.post("/admin/email-templates/{key}/test")
async def test_email_template(key: str, user: dict = Depends(require_perm("content:manage"))):
    """Sends the email to yourself with placeholder sample values, so you can read it before it goes out."""
    if key not in EMAIL_TEMPLATES:
        raise HTTPException(status_code=404, detail="Unknown email.")
    recent = await db.email_test_sends.find_one({"user_id": user["id"]}, sort=[("created_at", -1)])
    if recent and (now_utc() - datetime.fromisoformat(recent["created_at"])).total_seconds() < 15:
        raise HTTPException(status_code=429, detail="Give it a few seconds before sending another test.")
    await db.email_test_sends.insert_one({"user_id": user["id"], "key": key, "created_at": iso(now_utc())})
    samples = {"first_name": first_name(user.get("full_name")), "title": "Sample notification",
               "message": "This is what the wording looks like.", "org_name": "Nightfall Collective",
               "event_title": "Rooftop Jazz & Tapas Night", "city": "Dubai", "venue": "Sky Lounge",
               "host": "Nightfall Collective", "when": "Fri 04 Sep, 08:30 PM",
               "cancellation": "Free cancellation up to 24 hours before.",
               "receipt": "<p><b>Sample receipt</b><br/>1 ticket · $30.00</p>",
               "plan_name": "Buddilio Plus", "valid_until": "31 Dec 2026", "currency": BASE_CURRENCY,
               "total": "150.00", "intro": "3 payouts across 2 vendors are still pending.",
               "rows": "<tr><td style='padding:6px 0'><b>Nightfall Collective</b></td>"
                       "<td style='text-align:right'>$ 96.00</td></tr>",
               "reason": "The document was too blurry to read.", "role_label": "Operations",
               "inviter": user.get("full_name", "Buddilio"), "manager_name": "Ops Manager",
               "note": "Looking forward to hosting with you.", "invite_days": 14, "event_count": 12,
               "link_url": f"{FRONTEND_URL}/dashboard", "dashboard_url": f"{FRONTEND_URL}/dashboard",
               "welcome_url": f"{FRONTEND_URL}/welcome", "orders_url": f"{FRONTEND_URL}/orders",
               "membership_url": f"{FRONTEND_URL}/membership", "console_url": f"{FRONTEND_URL}/console",
               "partner_url": f"{FRONTEND_URL}/partner", "city_url": f"{FRONTEND_URL}/city/dubai",
               "guidelines_url": f"{FRONTEND_URL}/p/guidelines",
               "event_url": f"{FRONTEND_URL}/events/sample",
               "reset_url": f"{FRONTEND_URL}/reset-password?token=sample",
               "invite_url": f"{FRONTEND_URL}/vendor-signup?token=sample"}
    ok = await send_tpl(key, user["email"], samples)
    return {"ok": ok, "sent_to": user["email"],
            "message": "Check your inbox." if ok else
                       "The email provider rejected that address (in this sandbox only real inboxes accept mail)."}


@api.get("/admin/permissions")
async def list_permissions(user: dict = Depends(require_perm("team:manage"))):
    """The catalogue plus the presets, so the UI never hardcodes permission keys."""
    return {"groups": [{"group": g, "key": k, "description": d} for g, k, d in PERMISSIONS],
            "roles": [{"key": k, **{f: v for f, v in r.items()}} for k, r in STAFF_ROLES.items()],
            "my_permissions": sorted(perms_of(user))}


class TeamIn(BaseModel):
    full_name: str
    email: EmailStr
    staff_role: str
    scope: str = "admin"          # admin (control centre) | manager (vendor console)
    extra_permissions: List[str] = []


class TeamPatch(BaseModel):
    staff_role: Optional[str] = None
    extra_permissions: Optional[List[str]] = None
    status: Optional[str] = None


TEAM_FIELDS = {"full_name": 1, "email": 1, "role": 1, "staff_role": 1, "extra_permissions": 1,
               "status": 1, "created_at": 1, "org_name": 1}


def staff_view(doc: dict) -> dict:
    s = clean(doc)
    s["permissions"] = sorted(perms_of(doc | {"role": doc.get("role")}))
    s["role_label"] = STAFF_ROLES.get(doc.get("staff_role", ""), {}).get(
        "label", "Full access (legacy)" if doc.get("role") == "admin" else "Vendor manager (default)")
    return s


def check_grant(actor: dict, staff_role: str, extras: list, scope: str) -> list:
    """Nobody can hand out more than they hold, and the preset must match the surface."""
    preset = STAFF_ROLES.get(staff_role)
    if not preset or preset["scope"] != scope:
        raise HTTPException(status_code=400, detail="Pick a role that matches the chosen access area.")
    wanted = set(preset["permissions"]) | {e for e in extras if e in ALL_PERMISSIONS}
    held = perms_of(actor)
    over = wanted - held
    if over:
        raise HTTPException(status_code=403,
                            detail=f"You can't grant permissions you don't hold yourself: {', '.join(sorted(over))}.")
    return sorted({e for e in extras if e in ALL_PERMISSIONS} - set(preset["permissions"]))


@api.get("/admin/team")
async def list_team(user: dict = Depends(require_perm("team:manage"))):
    docs = await db.users.find({"role": {"$in": ["admin", "manager"]}}, TEAM_FIELDS) \
        .sort("created_at", 1).limit(200).to_list(200)
    return {"items": [staff_view(d) for d in docs]}


@api.post("/admin/team")
async def invite_team_member(payload: TeamIn, user: dict = Depends(require_perm("team:manage"))):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Someone already uses that email on Buddilio.")
    extras = check_grant(user, payload.staff_role, payload.extra_permissions, payload.scope)
    doc = {"full_name": payload.full_name.strip()[:80], "email": email,
           "role": "admin" if payload.scope == "admin" else "manager",
           "staff_role": payload.staff_role, "extra_permissions": extras,
           "password_hash": hash_password(secrets.token_urlsafe(18)), "status": "active",
           "city": "", "photo": "", "verified": True, "email_verified": False,
           "created_by": user["id"], "created_at": iso(now_utc())}
    res = await db.users.insert_one(doc)
    token = secrets.token_urlsafe(32)
    await db.password_reset_tokens.insert_one({
        "token": token, "user_id": str(res.inserted_id),
        "expires_at": now_utc() + timedelta(days=7), "created_at": iso(now_utc())})
    role_label = STAFF_ROLES[payload.staff_role]["label"]
    await send_tpl("team_invite", email, {
        "inviter": user["full_name"], "role_label": role_label,
        "reset_url": f"{FRONTEND_URL}/reset-password?token={token}"})
    await audit(user, "team.invite", "user", str(res.inserted_id),
                {"email": email, "staff_role": payload.staff_role, "scope": payload.scope})
    return staff_view(await db.users.find_one({"_id": res.inserted_id}, TEAM_FIELDS))


@api.patch("/admin/team/{uid}")
async def update_team_member(uid: str, payload: TeamPatch, user: dict = Depends(require_perm("team:manage"))):
    if uid == user["id"]:
        raise HTTPException(status_code=400, detail="You can't change your own permissions.")
    try:
        target = await db.users.find_one({"_id": ObjectId(uid), "role": {"$in": ["admin", "manager"]}})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid team member id")
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")
    if perms_of(target) - perms_of(user):
        raise HTTPException(status_code=403, detail="This person has permissions beyond yours, so you can't edit them.")
    upd: dict[str, Any] = {}
    if payload.staff_role is not None or payload.extra_permissions is not None:
        staff_role = payload.staff_role or target.get("staff_role") or ""
        scope = "admin" if target.get("role") == "admin" else "manager"
        extras = payload.extra_permissions if payload.extra_permissions is not None else (
            target.get("extra_permissions") or [])
        upd["extra_permissions"] = check_grant(user, staff_role, extras, scope)
        upd["staff_role"] = staff_role
    if payload.status is not None:
        if payload.status not in ("active", "suspended"):
            raise HTTPException(status_code=400, detail="Status must be active or suspended.")
        if payload.status == "suspended" and "team:manage" in perms_of(target):
            others = await db.users.count_documents({"role": "admin", "status": "active",
                                                     "_id": {"$ne": target["_id"]},
                                                     "$or": [{"staff_role": "super_admin"},
                                                             {"staff_role": {"$in": [None, ""]}}]})
            if not others:
                raise HTTPException(status_code=400, detail="Keep at least one active super admin.")
        upd["status"] = payload.status
    if not upd:
        raise HTTPException(status_code=400, detail="Nothing to change.")
    await db.users.update_one({"_id": target["_id"]}, {"$set": upd})
    await audit(user, "team.update", "user", uid, upd)
    return staff_view(await db.users.find_one({"_id": target["_id"]}, TEAM_FIELDS))


@api.get("/admin/managers")
async def admin_managers(user: dict = Depends(require_perm("team:manage"))):
    docs = await db.users.find({"role": "manager"},
                               {"full_name": 1, "email": 1, "org_name": 1, "status": 1, "mobile": 1,
                                "country": 1, "created_at": 1}).sort("created_at", -1).limit(200).to_list(200)
    items = []
    for d in docs:
        m = clean(d)
        m["vendors"] = await db.users.count_documents({"role": "partner", "managed_by": m["id"]})
        items.append(m)
    return {"items": items}


@api.patch("/admin/managers/{mid}")
async def admin_update_manager(mid: str, body: dict, user: dict = Depends(require_perm("team:manage"))):
    action = body.get("action")
    if action not in ("approve", "reject", "suspend"):
        raise HTTPException(status_code=400, detail="Unknown action")
    status = {"approve": "active", "reject": "rejected", "suspend": "suspended"}[action]
    doc = await db.users.find_one({"_id": ObjectId(mid), "role": "manager"})
    if not doc:
        raise HTTPException(status_code=404, detail="Manager not found")
    await db.users.update_one({"_id": doc["_id"]}, {"$set": {"status": status}})
    await audit(user, f"manager.{action}", "user", mid)
    if action == "approve":
        await notify(mid, "Console access approved",
                     "You can now add and manage vendors from the Buddilio console.", "console", "/console")
        await send_tpl("console_approved", doc["email"], {
            "first_name": first_name(doc.get("full_name")), "console_url": f"{FRONTEND_URL}/console"})
    return {"ok": True, "status": status}


# ---------------- vendor verification queue ----------------
VERIFY_STATES = ("pending", "verified", "rejected")


def verify_state(u: dict) -> str:
    if u.get("verification_status") in VERIFY_STATES:
        return u["verification_status"]
    return "verified" if u.get("verified") else "pending"


@api.get("/admin/verifications")
async def admin_verifications(status: str = "pending", user: dict = Depends(require_perm("verification:manage"))):
    """Every vendor with documents on file, so one admin can clear the whole queue."""
    docs = await db.users.find(
        {"role": "partner"},
        {"full_name": 1, "org_name": 1, "email": 1, "city": 1, "mobile": 1, "documents": 1,
         "verified": 1, "verification_status": 1, "verification_note": 1, "verified_at": 1,
         "managed_by": 1, "created_at": 1}).sort("created_at", -1).limit(500).to_list(500)
    managers = await load_many(db.users, [d.get("managed_by", "") for d in docs],
                               {"full_name": 1, "org_name": 1})
    items = []
    for d in docs:
        v = clean(d)
        v["verification_status"] = verify_state(d)
        v["documents"] = d.get("documents") or []
        v["document_count"] = len(v["documents"])
        mgr = managers.get(d.get("managed_by", ""))
        v["manager"] = (mgr.get("org_name") or mgr.get("full_name")) if mgr else ""
        if status and status != "all" and v["verification_status"] != status:
            continue
        if status == "pending" and not v["document_count"]:
            continue
        items.append(v)
    counts = {"pending": 0, "verified": 0, "rejected": 0}
    for d in docs:
        st = verify_state(d)
        if st == "pending" and not (d.get("documents") or []):
            continue
        counts[st] = counts.get(st, 0) + 1
    return {"items": items, "counts": counts}


class VerifyIn(BaseModel):
    action: str
    note: str = ""


@api.post("/admin/verifications/{vid}")
async def admin_verify_vendor(vid: str, payload: VerifyIn, user: dict = Depends(require_perm("verification:manage"))):
    if payload.action not in ("approve", "reject", "reset"):
        raise HTTPException(status_code=400, detail="Unknown action")
    try:
        vendor = await db.users.find_one({"_id": ObjectId(vid), "role": "partner"})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid vendor id")
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    if payload.action == "approve" and not (vendor.get("documents") or []):
        raise HTTPException(status_code=400, detail="This vendor hasn't uploaded any documents yet.")
    state = {"approve": "verified", "reject": "rejected", "reset": "pending"}[payload.action]
    upd = {"verification_status": state, "verified": state == "verified",
           "verification_note": payload.note[:400],
           "verified_at": iso(now_utc()) if state == "verified" else ""}
    await db.users.update_one({"_id": vendor["_id"]}, {"$set": upd})
    await audit(user, f"vendor.verify_{payload.action}", "user", vid, {"note": payload.note[:200]})
    name = vendor.get("org_name") or vendor.get("full_name") or "there"
    if state == "verified":
        await notify(vid, "You're verified", "Your documents checked out — the verified badge is now on your "
                     "profile and events.", "vendor", "/partner")
        await send_tpl("vendor_verified", vendor["email"],
                       {"org_name": name, "partner_url": f"{FRONTEND_URL}/partner"})
    elif state == "rejected":
        reason = payload.note.strip() or "We couldn't read the documents you sent."
        await notify(vid, "Verification needs attention", reason, "vendor", "/partner")
        await send_tpl("vendor_rejected", vendor["email"],
                       {"org_name": name, "reason": reason, "partner_url": f"{FRONTEND_URL}/partner"})
    return {"ok": True, "verification_status": state, "verified": state == "verified"}


class AutoReloadIn(BaseModel):
    enabled: bool = True
    threshold: float = Field(ge=0, le=100000)
    amount: float = Field(ge=500, le=200000)


@api.put("/wallet/auto-reload")
async def set_auto_reload(payload: AutoReloadIn, user: dict = Depends(get_current_user)):
    """Keep the wallet topped up so an accepted hangout never waits on a payment screen."""
    doc = await db.users.find_one({"_id": ObjectId(user["id"])}, {"saved_card": 1})
    if payload.enabled and not (doc or {}).get("saved_card"):
        raise HTTPException(status_code=400, detail="Save a card first — auto reload charges that card.")
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"auto_reload": {
        "enabled": payload.enabled, "threshold": round(payload.threshold, 2),
        "amount": round(payload.amount, 2), "updated_at": iso(now_utc())}}})
    return {"ok": True, "auto_reload": {"enabled": payload.enabled, "threshold": payload.threshold,
                                        "amount": payload.amount}}


async def run_auto_reload(user_id: str) -> float:
    """Charge the saved card and credit the wallet when the balance falls under the member's limit."""
    u = await db.users.find_one({"_id": ObjectId(user_id)}, {"auto_reload": 1, "saved_card": 1, "email": 1})
    cfg = (u or {}).get("auto_reload") or {}
    if not cfg.get("enabled") or not (u or {}).get("saved_card"):
        return 0.0
    balance = await credit_balance(user_id)
    if balance > float(cfg.get("threshold", 0)):
        return 0.0
    amount = round(float(cfg.get("amount", 0)), 2)
    charged = await charge_saved_card({"_id": ObjectId(user_id), "member_id": user_id,
                                       "item_name": "Wallet auto reload",
                                       "currency": BASE_CURRENCY}, amount)
    if not charged:
        return 0.0
    await db.orders.update_one({"_id": ObjectId(charged["id"])}, {"$set": {"kind": "wallet", "ref_id": ""}})
    await grant_credit(user_id, amount, f"Auto reload from your card ending {charged['last4']}", "")
    return amount


@api.post("/cron/rating-nudges")
async def cron_rating_nudges(_: None = Depends(cron_guard)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    asyncio.create_task(send_rating_nudges())
    return {"ok": True, "queued": "rating-nudges"}


async def send_rating_nudges() -> int:
    """A day after a hangout, nudge the guest once for their private rating."""
    since = iso(now_utc() - timedelta(days=3))
    until = iso(now_utc() - timedelta(hours=20))
    rows = await db.companion_bookings.find(
        {"status": "completed", "rated": {"$ne": True}, "nudged_at": {"$exists": False},
         "completed_at": {"$gte": since, "$lte": until}}).limit(200).to_list(200)
    sent = 0
    for b in rows:
        await notify(b["member_id"], "How was your hangout?",
                     "Leave a private rating — it only takes a second and helps other members choose well.",
                     "reminder", "/hangouts/bookings")
        await db.companion_bookings.update_one({"_id": b["_id"]}, {"$set": {"nudged_at": iso(now_utc())}})
        sent += 1
    logger.info(f"rating nudges sent: {sent}")
    return sent


# ---------------- member ID & address verification ----------------
ID_TYPE_KEYS = {d["key"] for d in ID_DOC_TYPES}


class IdVerificationIn(BaseModel):
    doc_type: str
    documents: List[dict] = []
    address: str = ""


@api.get("/me/admin-nav")
async def my_admin_nav(user: dict = Depends(get_current_user)):
    doc = await db.users.find_one({"_id": ObjectId(user["id"])}, {"admin_nav": 1})
    return {"favourites": ((doc or {}).get("admin_nav") or {}).get("favourites", [])}


@api.put("/me/admin-nav")
async def save_admin_nav(payload: dict = Body(...), user: dict = Depends(get_current_user)):
    favs = [str(x)[:40] for x in (payload.get("favourites") or [])][:12]
    await db.users.update_one({"_id": ObjectId(user["id"])},
                              {"$set": {"admin_nav": {"favourites": favs, "updated_at": iso(now_utc())}}})
    return {"favourites": favs}


@api.get("/me/verification")
async def my_verification(user: dict = Depends(get_current_user)):
    doc = await db.users.find_one({"_id": ObjectId(user["id"])},
                                  {"id_verification": 1, "verified": 1})
    return {"types": ID_DOC_TYPES, "verified": bool((doc or {}).get("verified")),
            "submission": (doc or {}).get("id_verification") or None}


@api.put("/me/verification")
async def submit_verification(payload: IdVerificationIn, user: dict = Depends(get_current_user)):
    if payload.doc_type not in ID_TYPE_KEYS:
        raise HTTPException(status_code=400, detail="Pick one of the accepted document types.")
    if not payload.documents or len(payload.documents) > 4:
        raise HTTPException(status_code=400, detail="Attach between one and four files.")
    files = []
    for d in payload.documents:
        url = str(d.get("url", ""))
        if not url.startswith("/api/files/"):
            raise HTTPException(status_code=400, detail="Upload your documents through Buddilio first.")
        files.append({"url": url, "name": str(d.get("name", "Document"))[:120]})
    sub = {"doc_type": payload.doc_type, "documents": files, "address": payload.address[:300],
           "status": "pending", "note": "", "submitted_at": iso(now_utc())}
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"id_verification": sub}})
    return {"ok": True, "submission": sub}


@api.post("/me/verification/start")
async def start_verification(payload: dict = Body(default={}), user: dict = Depends(get_current_user)):
    """Marks the check as started so we can nudge anyone who never finishes uploading."""
    doc = await db.users.find_one({"_id": ObjectId(user["id"])}, {"verified": 1, "id_verification": 1})
    if (doc or {}).get("verified"):
        return {"ok": True, "started": False}
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {
        "id_verification_started": {"doc_type": str(payload.get("doc_type", ""))[:40],
                                    "at": iso(now_utc()), "reminders": 0}}})
    return {"ok": True, "started": True}


@api.post("/cron/verification-reminders")
async def cron_verification_reminders(_: None = Depends(cron_guard)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    asyncio.create_task(send_verification_reminders())
    return {"ok": True, "queued": "verification-reminders"}


async def send_verification_reminders() -> int:
    """Two gentle nudges, a day apart, for members who opened the ID check but never sent it in."""
    cutoff = iso(now_utc() - timedelta(hours=24))
    rows = await db.users.find(
        {"verified": {"$ne": True}, "status": "active",
         "id_verification_started.at": {"$lte": cutoff},
         "id_verification_started.reminders": {"$lt": 2},
         "id_verification": {"$exists": False}},
        {"full_name": 1, "email": 1, "id_verification_started": 1}).limit(300).to_list(300)
    sent = 0
    for u in rows:
        uid = str(u["_id"])
        await notify(uid, "Finish your ID check",
                     "You're one upload away from the verified badge — add your document and we'll review it "
                     "within a day.", "reminder", "/profile")
        await db.users.update_one({"_id": u["_id"]},
                                  {"$inc": {"id_verification_started.reminders": 1},
                                   "$set": {"id_verification_started.reminded_at": iso(now_utc())}})
        sent += 1
    logger.info(f"verification reminders sent: {sent}")
    return sent


async def expire_vendor_documents() -> dict:
    """Reminds vendors 30/7/1 days before a mandatory document expires, then pauses them on expiry."""
    import agreements as agr
    mandatory = agr.REQUIRED_DOCS + agr.BANK_PROOF_DOCS
    today = now_utc()
    reminded, expired = 0, 0
    rows = await db.vendor_documents.find(
        {"doc_type": {"$in": mandatory}, "status": {"$in": ["approved", "pending"]},
         "expires_on": {"$gt": ""}}).limit(1000).to_list(1000)
    for doc in rows:
        try:
            due = datetime.fromisoformat(str(doc["expires_on"])[:10]).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        vendor = await db.vendor_profiles.find_one({"_id": ObjectId(doc["vendor_id"])}) \
            if ObjectId.is_valid(doc["vendor_id"]) else None
        if not vendor:
            continue
        label = doc["doc_type"].replace("_", " ")
        days_left = (due.date() - today.date()).days
        if days_left <= 0:
            if doc["status"] != "expired":
                await db.vendor_documents.update_one({"_id": doc["_id"]}, {"$set": {
                    "status": "expired", "note": "Expired — upload a current document.",
                    "expired_at": iso(now_utc())}})
                await db.vendor_profiles.update_one({"_id": vendor["_id"]}, {"$set": {
                    "status": "documents_required", "listings_paused": True,
                    "status_reason": f"{label.title()} expired", "status_changed_at": iso(now_utc())}})
                if vendor.get("user_id"):
                    await notify(vendor["user_id"], "Listings paused — document expired",
                                 f"Your {label} expired, so your Buddilio listings are paused. Upload a "
                                 "current document to go live again.", "vendor", "/vendor/agreement")
                await send_tpl("vendor_document_expiring", vendor.get("email", ""),
                               {"first_name": first_name(vendor.get("contact_person", "")),
                                "document": label.title(), "days": "0",
                                "expires_on": str(doc["expires_on"])[:10],
                                "portal_url": f"{FRONTEND_URL}/vendor/agreement"})
                expired += 1
            continue
        if days_left in (30, 7, 1) and str(doc.get("reminded_for", "")) != str(days_left):
            await db.vendor_documents.update_one({"_id": doc["_id"]},
                                                 {"$set": {"reminded_for": str(days_left),
                                                           "reminded_at": iso(now_utc())}})
            if vendor.get("user_id"):
                await notify(vendor["user_id"], f"{label.title()} expires in {days_left} day(s)",
                             "Upload a current document so your listings stay live.", "vendor",
                             "/vendor/agreement")
            await send_tpl("vendor_document_expiring", vendor.get("email", ""),
                           {"first_name": first_name(vendor.get("contact_person", "")),
                            "document": label.title(), "days": str(days_left),
                            "expires_on": str(doc["expires_on"])[:10],
                            "portal_url": f"{FRONTEND_URL}/vendor/agreement"})
            reminded += 1
    logger.info(f"vendor documents — reminded {reminded}, expired {expired}")
    return {"reminded": reminded, "expired": expired}


async def send_membership_renewal_reminders() -> int:
    """One nudge, 7 days out, for memberships that will not auto-renew."""
    start = iso(now_utc() + timedelta(days=6))
    end = iso(now_utc() + timedelta(days=8))
    rows = await db.user_memberships.find(
        {"status": "active", "ends_at": {"$gte": start, "$lte": end},
         "auto_renews": {"$ne": True}, "renewal_reminded": {"$ne": True}}).limit(500).to_list(500)
    sent = 0
    for m in rows:
        user = await db.users.find_one({"_id": ObjectId(m["user_id"])}, {"full_name": 1, "email": 1})
        if not user:
            continue
        await db.user_memberships.update_one({"_id": m["_id"]}, {"$set": {
            "renewal_reminded": True, "renewal_reminded_at": iso(now_utc())}})
        await notify(m["user_id"], "Your membership ends in a week",
                     f"{m.get('plan_name', 'Your plan')} ends on {str(m['ends_at'])[:10]}. "
                     "Renew to keep your benefits.", "membership", "/membership")
        await send_tpl("membership_expiring", user.get("email", ""),
                       {"first_name": first_name(user.get("full_name", "")),
                        "plan_name": m.get("plan_name", "Buddilio"), "days": "7",
                        "ends_on": str(m["ends_at"])[:10],
                        "membership_url": f"{FRONTEND_URL}/membership"})
        sent += 1
    logger.info(f"membership renewal reminders sent: {sent}")
    return sent


async def send_pass_reminders() -> int:
    """Emails the QR voucher a configurable number of hours before the event (default 12)."""
    s = await db.settings.find_one({}, {"pass_reminder_hours": 1}) or {}
    try:
        hours = int(s.get("pass_reminder_hours") or 12)
    except (TypeError, ValueError):
        hours = 12
    hours = min(max(hours, 1), 168)
    now = now_utc()
    rows = await db.passes.find({"status": "valid", "kind": "event",
                                 "starts_at": {"$gte": iso(now),
                                               "$lte": iso(now + timedelta(hours=hours))},
                                 "reminded": {"$ne": True}}).limit(1000).to_list(1000)
    sent = 0
    for p in rows:
        if not ObjectId.is_valid(p.get("user_id") or ""):
            # Door walk-ins can belong to a guest with no account — nothing to email.
            await db.passes.update_one({"_id": p["_id"]}, {"$set": {"reminded": True}})
            continue
        try:
            user = await db.users.find_one({"_id": ObjectId(p["user_id"])}, {"full_name": 1, "email": 1})
        except Exception as exc:
            logger.warning(f"pass reminder skipped for {p.get('code')}: {exc}")
            continue
        if not user:
            continue
        await db.passes.update_one({"_id": p["_id"]}, {"$set": {"reminded": True,
                                                               "reminded_at": iso(now_utc())}})
        await send_tpl("pass_reminder", user.get("email", ""),
                       {"first_name": first_name(user.get("full_name", "")),
                        "item": p["item_name"], "code": p["code"],
                        "when": str(p.get("starts_at") or "")[:16].replace("T", " at "),
                        "where": p.get("city") or "the venue",
                        "qr_url": f"{FRONTEND_URL.rstrip('/')}/api/passes/{p['code']}/qr.png",
                        "pass_url": pass_verify_url(p["code"])})
        await notify(p["user_id"], "Your pass is ready",
                     f"{p['item_name']} is coming up. Show code {p['code']} or the QR at the door.",
                     "reminder", "/orders", email=False)
        sent += 1
    logger.info(f"pass reminders sent: {sent}")
    return sent


@api.post("/cron/daily-maintenance")
async def cron_daily_maintenance(_: None = Depends(cron_guard)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    asyncio.create_task(send_verification_reminders())
    asyncio.create_task(expire_vendor_documents())
    asyncio.create_task(send_membership_renewal_reminders())
    asyncio.create_task(send_pass_reminders())
    if now_utc().day == 1:
        asyncio.create_task(generate_monthly_commission_invoices())
    return {"ok": True, "queued": ["verification-reminders", "vendor-doc-expiry",
                                   "membership-renewal-reminders", "pass-reminders"]}


async def generate_monthly_commission_invoices() -> dict:
    """Invoices Buddilio's commission + platform fee to each vendor for the previous month."""
    import vendor_routes
    period = (now_utc().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    build = vendor_routes.D.get("build_commission_invoice")
    if not build:
        return {"created": 0}
    made = 0
    for v in await db.vendor_profiles.find({}, {"_id": 1}).limit(500).to_list(500):
        if await build(str(v["_id"]), period, "cron"):
            made += 1
    logger.info(f"commission invoices for {period}: {made}")
    return {"period": period, "created": made}


@api.post("/cron/commission-invoices")
async def cron_commission_invoices(_: None = Depends(cron_guard)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    asyncio.create_task(generate_monthly_commission_invoices())
    return {"ok": True, "queued": "commission-invoices"}


@api.post("/cron/vendor-doc-expiry")
async def cron_vendor_doc_expiry(_: None = Depends(cron_guard)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    asyncio.create_task(expire_vendor_documents())
    return {"ok": True, "queued": "vendor-doc-expiry"}


@api.get("/admin/id-verifications")
async def admin_id_verifications(status: str = "pending",
                                 user: dict = Depends(require_perm("verification:manage"))):
    flt: dict[str, Any] = {"id_verification": {"$exists": True}}
    if status and status != "all":
        flt["id_verification.status"] = status
    docs = await db.users.find(flt, {"full_name": 1, "email": 1, "city": 1, "country": 1, "photo": 1,
                                     "verified": 1, "id_verification": 1}) \
        .sort("id_verification.submitted_at", -1).limit(300).to_list(300)
    counts = {s: await db.users.count_documents({"id_verification.status": s})
              for s in ("pending", "verified", "rejected")}
    return {"items": [clean(d) for d in docs], "counts": counts, "types": ID_DOC_TYPES}


@api.post("/admin/id-verifications/{uid}")
async def moderate_id_verification(uid: str, payload: VerifyIn,
                                   user: dict = Depends(require_perm("verification:manage"))):
    if payload.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Unknown action")
    try:
        doc = await db.users.find_one({"_id": ObjectId(uid), "id_verification": {"$exists": True}})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid member id")
    if not doc:
        raise HTTPException(status_code=404, detail="Nothing submitted by that member.")
    state = "verified" if payload.action == "approve" else "rejected"
    await db.users.update_one({"_id": doc["_id"]}, {"$set": {
        "id_verification.status": state, "id_verification.note": payload.note[:300],
        "id_verification.reviewed_at": iso(now_utc()), "verified": state == "verified"}})
    await audit(user, f"id_verification.{payload.action}", "user", uid, {"note": payload.note[:120]})
    await notify(uid, "ID check " + state,
                 "You're verified — the badge is on your profile." if state == "verified"
                 else (payload.note or "We couldn't read your documents. Please upload clearer copies."),
                 "moderation", "/profile")
    return {"ok": True, "status": state}


# ---------------- public host profiles ----------------
HOST_FIELDS = {"full_name": 1, "org_name": 1, "photo": 1, "city": 1, "country": 1, "bio": 1,
               "verified": 1, "rating": 1, "rating_count": 1, "created_at": 1, "website": 1}


async def host_cards(docs: list) -> list:
    ids = [str(d["_id"]) for d in docs]
    stats = await vendor_stats(ids)
    follows: dict[str, int] = {}
    for f in await db.host_follows.aggregate([{"$match": {"host_id": {"$in": ids}}},
                                              {"$group": {"_id": "$host_id", "n": {"$sum": 1}}}]).to_list(500):
        follows[f["_id"]] = f["n"]
    out = []
    for d in docs:
        h = clean(d)
        h["name"] = d.get("org_name") or d.get("full_name")
        s = stats.get(h["id"], {})
        h["events"] = s.get("published", 0)
        h["seats_sold"] = s.get("seats_sold", 0)
        h["followers"] = follows.get(h["id"], 0)
        out.append(h)
    return out


@api.get("/hosts")
async def list_hosts(q: str = "", city: str = "", verified_only: bool = False,
                     page: int = 1, limit: int = 12):
    """A browsable directory of organisers — verified ones first."""
    flt: dict[str, Any] = {"role": "partner", "status": {"$ne": "banned"}}
    if verified_only:
        flt["verified"] = True
    if city:
        flt["city"] = city
    if q:
        flt["$or"] = [{"org_name": {"$regex": q, "$options": "i"}},
                      {"full_name": {"$regex": q, "$options": "i"}}]
    total = await db.users.count_documents(flt)
    docs = await db.users.find(flt, HOST_FIELDS).sort([("verified", -1), ("rating", -1)]) \
        .skip((page - 1) * limit).limit(limit).to_list(limit)
    return {"items": await host_cards(docs), "total": total, "page": page}


@api.get("/hosts/{hid}")
async def host_profile(hid: str, user: Optional[dict] = Depends(optional_user)):
    try:
        doc = await db.users.find_one({"_id": ObjectId(hid), "role": "partner"}, HOST_FIELDS)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid organiser id")
    if not doc:
        raise HTTPException(status_code=404, detail="Organiser not found")
    host = (await host_cards([doc]))[0]
    now = iso(now_utc())
    upcoming = await db.events.find({"partner_id": hid, "status": "published", "starts_at": {"$gte": now}}) \
        .sort("starts_at", 1).limit(12).to_list(12)
    past = await db.events.find({"partner_id": hid, "status": {"$in": ["published", "completed"]},
                                "starts_at": {"$lt": now}}).sort("starts_at", -1).limit(9).to_list(9)
    host["upcoming"] = [clean(e) | {"partner_verified": host.get("verified", False)} for e in upcoming]
    host["past"] = [clean(e) | {"partner_verified": host.get("verified", False)} for e in past]
    photo_rows = await db.event_photos.find(
        {"event_id": {"$in": [str(e["_id"]) for e in past + upcoming]}, "hidden": {"$ne": True}}) \
        .sort("created_at", -1).limit(12).to_list(12)
    host["photos"] = [{"url": p["url"], "event_id": p["event_id"], "caption": p.get("caption", "")}
                      for p in photo_rows]
    revs = await db.reviews.find({"partner_id": hid, **VISIBLE_REVIEW}, {"rating": 1, "comment": 1}) \
        .sort("rating", -1).limit(3).to_list(3)
    host["reviews"] = [{"rating": r["rating"], "comment": (r.get("comment") or "")[:180]}
                       for r in revs if r.get("comment")]
    host["is_following"] = bool(user) and bool(
        await db.host_follows.find_one({"user_id": user["id"], "host_id": hid}))
    return host


@api.post("/hosts/{hid}/follow")
async def follow_host(hid: str, user: dict = Depends(get_current_user)):
    host = await db.users.find_one({"_id": ObjectId(hid), "role": "partner"}, {"org_name": 1, "full_name": 1})
    if not host:
        raise HTTPException(status_code=404, detail="Organiser not found")
    existing = await db.host_follows.find_one({"user_id": user["id"], "host_id": hid})
    if existing:
        await db.host_follows.delete_one({"_id": existing["_id"]})
        following = False
    else:
        await db.host_follows.insert_one({"user_id": user["id"], "host_id": hid,
                                          "created_at": iso(now_utc())})
        following = True
    return {"ok": True, "following": following,
            "followers": await db.host_follows.count_documents({"host_id": hid})}


@api.get("/me/following")
async def my_following(user: dict = Depends(get_current_user)):
    rows = await db.host_follows.find({"user_id": user["id"]}).sort("created_at", -1).limit(100).to_list(100)
    hosts = await db.users.find({"_id": {"$in": [ObjectId(r["host_id"]) for r in rows if len(r["host_id"]) == 24]}},
                                HOST_FIELDS).limit(100).to_list(100)
    return {"items": await host_cards(hosts)}


async def notify_followers(partner_id: str, ev: dict) -> int:
    """Following an organiser means hearing about their next night first."""
    rows = await db.host_follows.find({"host_id": partner_id}, {"user_id": 1}).limit(2000).to_list(2000)
    host = await db.users.find_one({"_id": ObjectId(partner_id)}, {"org_name": 1, "full_name": 1})
    name = (host or {}).get("org_name") or (host or {}).get("full_name") or "An organiser you follow"
    for r in rows:
        await notify(r["user_id"], f"{name} just announced something",
                     f"{ev['title']} in {ev.get('city', '')} is now open for bookings.",
                     "event", f"/events/{str(ev['_id'])}")
    return len(rows)


# ---------------- shareable recap card ----------------
RECAP_SIZE = (1080, 1350)


def draw_recap(photos: list[bytes], title: str, meta: str, footer: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    card = Image.new("RGB", RECAP_SIZE, (15, 23, 42))
    grid_h = 900
    cells = [(0, 0, 540, 450), (540, 0, 540, 450), (0, 450, 540, 450), (540, 450, 540, 450)]
    if len(photos) == 1:
        cells = [(0, 0, 1080, grid_h)]
    elif len(photos) == 2:
        cells = [(0, 0, 540, grid_h), (540, 0, 540, grid_h)]
    elif len(photos) == 3:
        cells = [(0, 0, 1080, 500), (0, 500, 540, 400), (540, 500, 540, 400)]
    for raw, (x, y, w, h) in zip(photos[:len(cells)], cells):
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            continue
        scale = max(w / img.width, h / img.height)
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
        left = (img.width - w) // 2
        top = (img.height - h) // 2
        card.paste(img.crop((left, top, left + w, top + h)), (x, y))
    d = ImageDraw.Draw(card)

    def font(size: int, bold: bool = False):
        path = "/usr/share/fonts/truetype/liberation/LiberationSans%s.ttf" % ("-Bold" if bold else "-Regular")
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    d.rectangle([0, grid_h, 1080, 1350], fill=(15, 23, 42))
    words, lines, cur = title.split(), [], ""
    big = font(60, True)
    for w in words:
        trial = f"{cur} {w}".strip()
        if d.textlength(trial, font=big) > 980 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    lines.append(cur)
    y = grid_h + 60
    for line in lines[:2]:
        d.text((50, y), line, font=big, fill=(255, 255, 255))
        y += 74
    d.text((50, y + 10), meta, font=font(36), fill=(148, 163, 184))
    d.text((50, 1250), footer, font=font(34, True), fill=(236, 72, 153))
    out = io.BytesIO()
    card.save(out, format="JPEG", quality=88)
    return out.getvalue()


@api.get("/events/{event_id}/recap")
async def event_recap(event_id: str, user: Optional[dict] = Depends(optional_user)):
    """The ingredients of the shareable card, plus the cached image if one exists."""
    ev = await public_event(event_id)
    photos = await db.event_photos.find({"event_id": event_id, "hidden": {"$ne": True}}) \
        .sort("created_at", -1).limit(4).to_list(4)
    cached = await db.event_recaps.find_one({"event_id": event_id})
    going = await db.event_participants.count_documents({"event_id": event_id, "status": "confirmed"})
    return {"event_id": event_id, "title": ev["title"], "city": ev.get("city", ""),
            "starts_at": ev.get("starts_at", ""), "host": ev.get("partner_name", ""),
            "going": going, "rating": ev.get("rating", 0),
            "photos": [p["url"] for p in photos], "photo_count": len(photos),
            "card_url": (cached or {}).get("card_url", ""),
            "share_url": f"{FRONTEND_URL}/events/{event_id}",
            "can_make": bool(photos) and bool(user)}


@api.post("/events/{event_id}/recap")
async def make_event_recap(event_id: str, user: dict = Depends(get_current_user)):
    ev = await public_event(event_id)
    photos = await db.event_photos.find({"event_id": event_id, "hidden": {"$ne": True}}) \
        .sort("created_at", -1).limit(4).to_list(4)
    if not photos:
        raise HTTPException(status_code=400, detail="Add a photo to the wall first — the card is built from them.")
    signature = "|".join(p["url"] for p in photos)
    cached = await db.event_recaps.find_one({"event_id": event_id})
    if cached and cached.get("signature") == signature:
        return {"ok": True, "card_url": cached["card_url"], "cached": True,
                "share_url": f"{FRONTEND_URL}/events/{event_id}"}
    blobs = []
    for p in photos:
        path = p["url"].split("/api/files/", 1)[-1]
        try:
            data, _ = await asyncio.to_thread(get_object, path)
            blobs.append(data)
        except Exception as e:
            logger.error(f"recap fetch failed: {e}")
    if not blobs:
        raise HTTPException(status_code=502, detail="Couldn't read those photos. Please try again.")
    going = await db.event_participants.count_documents({"event_id": event_id, "status": "confirmed"})
    when = (ev.get("starts_at") or "")[:10]
    meta = f"{ev.get('city', '')} · {when} · {going} went"
    try:
        card = await asyncio.to_thread(draw_recap, blobs, ev["title"], meta, "buddilio.com")
    except Exception as e:
        logger.error(f"recap render failed: {e}")
        raise HTTPException(status_code=502, detail="Couldn't build the card. Please try again.")
    path = f"{APP_NAME}/recaps/{event_id}/{uuid.uuid4()}.jpg"
    result = await asyncio.to_thread(put_object, path, card, "image/jpeg")
    await register_file(user["id"], result, f"{ev['title'][:60]} recap.jpg", "image/jpeg", len(card))
    card_url = f"/api/files/{result['path']}"
    await db.event_recaps.update_one(
        {"event_id": event_id},
        {"$set": {"card_url": card_url, "signature": signature, "photos": len(blobs),
                  "created_by": user["id"], "created_at": iso(now_utc())}}, upsert=True)
    return {"ok": True, "card_url": card_url, "cached": False,
            "share_url": f"{FRONTEND_URL}/events/{event_id}"}


# ---------------- weekly payout reminders ----------------
def week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def next_monday(dt: datetime) -> str:
    days = (7 - dt.weekday()) % 7 or 7
    return iso((dt + timedelta(days=days)).replace(hour=3, minute=30, second=0, microsecond=0))


async def payout_digest(manager: dict) -> dict:
    """What one manager's Monday reminder will say — shared by the cron and the console preview."""
    mid = manager["id"] if "id" in manager else str(manager["_id"])
    vendors = await db.users.find({"role": "partner", "managed_by": mid},
                                  {"org_name": 1, "full_name": 1}).limit(500).to_list(500)
    names = {str(v["_id"]): v.get("org_name") or v.get("full_name") for v in vendors}
    rows = []
    if names:
        rows = await db.payouts.find({"partner_id": {"$in": list(names)}, "status": "pending"}) \
            .sort("created_at", 1).limit(500).to_list(500)
    total = round(sum(float(r.get("net") or 0) for r in rows), 2)
    items = [{"vendor": names.get(r["partner_id"], "—"), "event_title": r.get("event_title", ""),
              "net": float(r.get("net") or 0), "currency": r.get("currency", BASE_CURRENCY),
              "due_since": r.get("created_at", "")} for r in rows]
    first = manager.get("full_name", "there").split(" ")[0]
    vendor_count = len({r["partner_id"] for r in rows})
    subject = f"Payouts due this week — {BASE_CURRENCY} {total:,.2f}"
    intro = (f"Hi {first}, {len(rows)} payout{'' if len(rows) == 1 else 's'} across {vendor_count} vendor"
             f"{'' if vendor_count == 1 else 's'} are still pending.")
    lines = "".join(
        f"<tr><td style='padding:6px 0'><b>{i['vendor']}</b><br>"
        f"<span style='color:#94A3B8;font-size:13px'>{i['event_title']}</span></td>"
        f"<td style='padding:6px 0;text-align:right;white-space:nowrap'>"
        f"{i['currency']} {i['net']:,.2f}</td></tr>" for i in items[:40])
    values = {"first_name": first, "intro": intro, "rows": lines, "total": f"{total:,.2f}",
              "currency": BASE_CURRENCY, "console_url": f"{FRONTEND_URL}/console"}
    tpl = await email_template("payout_reminder")
    return {"manager_id": mid, "email": manager.get("email", ""),
            "subject": fill(tpl["subject"], values), "intro": intro,
            "items": items, "total": total, "currency": BASE_CURRENCY, "vendors": vendor_count,
            "values": values, "will_send": bool(rows)}


async def send_payout_reminders() -> dict:
    """Monday nudge: every manager gets the list of what their vendors are still owed."""
    wk = week_key(now_utc())
    managers = await db.users.find({"role": "manager", "status": "active"},
                                   {"full_name": 1, "email": 1}).limit(500).to_list(500)
    sent = 0
    for m in managers:
        mid = str(m["_id"])
        if await db.payout_reminders.find_one({"manager_id": mid, "week": wk}):
            continue
        digest = await payout_digest(clean(dict(m)))
        if not digest["will_send"]:
            continue
        ok = await send_tpl("payout_reminder", m["email"], digest["values"])
        await db.payout_reminders.insert_one({
            "manager_id": mid, "week": wk, "payouts": len(digest["items"]), "total": digest["total"],
            "email_sent": ok, "created_at": iso(now_utc())})
        sent += 1
    logger.info(f"payout reminders: {sent} managers emailed for {wk}")
    return {"week": wk, "managers": sent}


@api.get("/console/payout-reminder")
async def console_payout_reminder(user: dict = Depends(require_perm("payouts:view"))):
    """Exactly what Monday's email will say, so managers are never surprised by it."""
    digest = await payout_digest(user)
    last = await db.payout_reminders.find_one({"manager_id": user["id"]}, sort=[("created_at", -1)])
    return {**{k: v for k, v in digest.items() if k not in ("html", "values")},
            "next_send_at": next_monday(now_utc()), "schedule": "Every Monday, 09:00 IST",
            "already_sent_this_week": bool(last and last.get("week") == week_key(now_utc())),
            "last_sent_at": (last or {}).get("created_at", ""),
            "recipient": user.get("email", "")}


@api.post("/cron/payout-reminders")
async def cron_payout_reminders(_: None = Depends(cron_guard)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    asyncio.create_task(send_payout_reminders())
    return {"ok": True, "queued": "payout-reminders", "week": week_key(now_utc())}


# ---------------- event photo wall ----------------
MAX_EVENT_PHOTOS = 10


class EventPhotoIn(BaseModel):
    url: str
    caption: str = ""


async def public_event(event_id: str) -> dict:
    try:
        ev = await db.events.find_one({"_id": ObjectId(event_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event id")
    if not ev or ev.get("status") not in ("published", "completed"):
        raise HTTPException(status_code=404, detail="Event not found")
    return ev


@api.get("/events/{event_id}/photos")
async def event_photos(event_id: str, user: Optional[dict] = Depends(optional_user)):
    """The photo wall — what the last crowd actually saw."""
    ev = await public_event(event_id)
    flt: dict[str, Any] = {"event_id": event_id}
    if not (user and user["role"] == "admin"):
        flt["hidden"] = {"$ne": True}
    rows = await db.event_photos.find(flt).sort("created_at", -1).limit(120).to_list(120)
    owners = await load_many(db.users, [r["user_id"] for r in rows], {"full_name": 1, "photo": 1})
    is_host = bool(user) and (user["role"] == "admin" or ev.get("partner_id") == user["id"])
    items = []
    for r in rows:
        o = owners.get(r["user_id"], {})
        items.append({"id": str(r["_id"]), "url": r["url"], "caption": r.get("caption", ""),
                      "user_id": r["user_id"], "user_name": short_name(o.get("full_name", "Member")),
                      "user_photo": o.get("photo", ""), "created_at": r.get("created_at", ""),
                      "hidden": bool(r.get("hidden")), "report_count": r.get("report_count", 0),
                      "reported_by_me": bool(user) and user["id"] in (r.get("reported_by") or []),
                      "can_delete": is_host or (bool(user) and r["user_id"] == user["id"])})
    can_post, reason = False, ""
    if not user:
        reason = "Log in to add your photos."
    elif ev["starts_at"] > iso(now_utc()):
        reason = "The wall opens when the event starts."
    else:
        part = await db.event_participants.find_one(
            {"event_id": event_id, "user_id": user["id"], "status": "confirmed"})
        mine = await db.event_photos.count_documents({"event_id": event_id, "user_id": user["id"]})
        if not part:
            reason = "Only people who went can post here."
        elif mine >= MAX_EVENT_PHOTOS:
            reason = f"You've added your {MAX_EVENT_PHOTOS} photos for this event."
        else:
            can_post = True
    return {"items": items, "count": len(items), "can_post": can_post, "reason": reason,
            "max_per_member": MAX_EVENT_PHOTOS}


@api.post("/events/{event_id}/photos")
async def add_event_photo(event_id: str, payload: EventPhotoIn, user: dict = Depends(get_current_user)):
    ev = await public_event(event_id)
    if ev["starts_at"] > iso(now_utc()):
        raise HTTPException(status_code=400, detail="The photo wall opens once the event starts.")
    if not await db.event_participants.find_one(
            {"event_id": event_id, "user_id": user["id"], "status": "confirmed"}):
        raise HTTPException(status_code=403, detail="Only confirmed attendees can post to this wall.")
    if not payload.url.startswith("/api/files/"):
        raise HTTPException(status_code=400, detail="Upload your photo through Buddilio first.")
    if await db.event_photos.count_documents({"event_id": event_id, "user_id": user["id"]}) >= MAX_EVENT_PHOTOS:
        raise HTTPException(status_code=400,
                            detail=f"You can add up to {MAX_EVENT_PHOTOS} photos per event.")
    doc = {"event_id": event_id, "user_id": user["id"], "url": payload.url,
           "caption": payload.caption.strip()[:200], "created_at": iso(now_utc())}
    res = await db.event_photos.insert_one(dict(doc))
    if ev.get("partner_id") and ev["partner_id"] != user["id"]:
        await notify(ev["partner_id"], "New photo on your event",
                     f"{short_name(user['full_name'])} added a photo to {ev['title']}.",
                     "event", f"/events/{event_id}")
    return {"ok": True, "id": str(res.inserted_id), **doc}


@api.delete("/events/{event_id}/photos/{pid}")
async def delete_event_photo(event_id: str, pid: str, user: dict = Depends(get_current_user)):
    try:
        photo = await db.event_photos.find_one({"_id": ObjectId(pid), "event_id": event_id})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid photo id")
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    ev = await db.events.find_one({"_id": ObjectId(event_id)}, {"partner_id": 1})
    allowed = (photo["user_id"] == user["id"] or user["role"] == "admin"
               or (ev or {}).get("partner_id") == user["id"])
    if not allowed:
        raise HTTPException(status_code=403, detail="You can only remove your own photos.")
    await db.event_photos.delete_one({"_id": photo["_id"]})
    return {"ok": True}


class PhotoReportIn(BaseModel):
    reason: str = ""


@api.post("/events/{event_id}/photos/{pid}/report")
async def report_event_photo(event_id: str, pid: str, payload: PhotoReportIn,
                             user: dict = Depends(get_current_user)):
    """Members flag a photo; it stays up until an admin looks at it."""
    try:
        photo = await db.event_photos.find_one({"_id": ObjectId(pid), "event_id": event_id})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid photo id")
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo["user_id"] == user["id"]:
        raise HTTPException(status_code=400, detail="That's your own photo.")
    if user["id"] in (photo.get("reported_by") or []):
        return {"ok": True, "message": "You've already reported this photo."}
    await db.event_photos.update_one({"_id": photo["_id"]},
                                     {"$inc": {"report_count": 1},
                                      "$addToSet": {"reported_by": user["id"]},
                                      "$set": {"last_reported_at": iso(now_utc()),
                                               "last_report_reason": payload.reason.strip()[:200]}})
    await db.reports.insert_one({
        "reporter_id": user["id"], "reporter_email": user["email"], "target_type": "photo",
        "target_id": pid, "reason": payload.reason.strip()[:200] or "Inappropriate photo",
        "details": f"event:{event_id}", "status": "open", "created_at": iso(now_utc())})
    return {"ok": True, "message": "Thanks — our safety team will review it."}


@api.get("/admin/photos")
async def admin_photos(status: str = "reported", user: dict = Depends(require_perm("moderation:manage"))):
    """Reported and hidden photos in one place."""
    flt: dict[str, Any] = {}
    if status == "reported":
        flt = {"report_count": {"$gt": 0}, "hidden": {"$ne": True}}
    elif status == "hidden":
        flt = {"hidden": True}
    else:
        flt = {}
    rows = await db.event_photos.find(flt).sort("last_reported_at", -1).limit(200).to_list(200)
    owners = await load_many(db.users, [r["user_id"] for r in rows], {"full_name": 1, "email": 1, "warnings": 1})
    events = await load_many(db.events, [r["event_id"] for r in rows], {"title": 1})
    items = []
    for r in rows:
        o = owners.get(r["user_id"], {})
        items.append({"id": str(r["_id"]), "url": r["url"], "caption": r.get("caption", ""),
                      "event_id": r["event_id"], "event_title": (events.get(r["event_id"]) or {}).get("title", ""),
                      "user_id": r["user_id"], "user_name": o.get("full_name", "Member"),
                      "user_email": o.get("email", ""), "warnings": o.get("warnings", 0),
                      "report_count": r.get("report_count", 0), "hidden": bool(r.get("hidden")),
                      "last_report_reason": r.get("last_report_reason", ""),
                      "created_at": r.get("created_at", ""), "warned": bool(r.get("warned_at"))})
    return {"items": items,
            "counts": {"reported": await db.event_photos.count_documents(
                           {"report_count": {"$gt": 0}, "hidden": {"$ne": True}}),
                       "hidden": await db.event_photos.count_documents({"hidden": True})}}


class PhotoModerateIn(BaseModel):
    action: str
    note: str = ""
    warn: bool = False


@api.post("/admin/photos/{pid}")
async def moderate_photo(pid: str, payload: PhotoModerateIn, user: dict = Depends(require_perm("moderation:manage"))):
    if payload.action not in ("hide", "restore", "delete", "dismiss"):
        raise HTTPException(status_code=400, detail="Unknown action")
    try:
        photo = await db.event_photos.find_one({"_id": ObjectId(pid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid photo id")
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    reason = payload.note.strip()[:300]
    if payload.action == "delete":
        await db.event_photos.delete_one({"_id": photo["_id"]})
    elif payload.action == "hide":
        await db.event_photos.update_one({"_id": photo["_id"]},
                                         {"$set": {"hidden": True, "hidden_reason": reason,
                                                   "hidden_at": iso(now_utc())}})
    elif payload.action == "restore":
        await db.event_photos.update_one({"_id": photo["_id"]},
                                         {"$set": {"hidden": False, "report_count": 0, "reported_by": [],
                                                   "last_report_reason": "", "last_reported_at": ""}})
    else:
        await db.event_photos.update_one({"_id": photo["_id"]},
                                         {"$set": {"report_count": 0, "reported_by": []}})
    await db.reports.update_many({"target_type": "photo", "target_id": pid, "status": "open"},
                                 {"$set": {"status": "resolved", "resolution": payload.action,
                                           "resolved_at": iso(now_utc())}})
    warned = False
    if payload.warn and payload.action in ("hide", "delete"):
        ev = await db.events.find_one({"_id": ObjectId(photo["event_id"])}, {"title": 1})
        owner = await db.users.find_one({"_id": ObjectId(photo["user_id"])}, {"email": 1, "full_name": 1})
        await db.users.update_one({"_id": ObjectId(photo["user_id"])},
                                  {"$inc": {"warnings": 1},
                                   "$set": {"last_warned_at": iso(now_utc())}})
        await db.event_photos.update_one({"_id": photo["_id"]}, {"$set": {"warned_at": iso(now_utc())}})
        text = reason or "It didn't meet our photo guidelines."
        await notify(photo["user_id"], "A photo of yours was removed",
                     f"{text} Please keep the photo wall respectful — repeat issues can suspend your account.",
                     "warning", f"/events/{photo['event_id']}")
        if owner:
            await send_tpl("photo_removed", owner["email"], {
                "first_name": first_name(owner.get("full_name")),
                "event_title": (ev or {}).get("title", "an event"), "reason": text,
                "guidelines_url": f"{FRONTEND_URL}/guidelines"})
        warned = True
    await audit(user, f"photo.{payload.action}", "photo", pid, {"warn": warned, "note": reason[:120]})
    return {"ok": True, "action": payload.action, "warned": warned}



# ---------------- dynamic pages, site content, profiles & events ----------------
class PageIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    slug: str
    title: str
    content: str = ""                     # rich text / markdown fallback
    blocks: List[dict] = []               # [{type, heading, text, image, items, cta_label, cta_url}]
    seo_title: str = ""
    seo_description: str = ""
    status: Literal["published", "draft"] = "published"
    nav_header: bool = False
    nav_footer_group: str = ""            # Explore | Company | Trust & Safety | ""
    nav_label: str = ""
    order: int = 0
    material_change: bool = False         # forces members to re-accept Terms/Privacy


BLOCK_TYPES = ("heading", "text", "richtext", "image", "quote", "list", "faq", "cta", "html")
SAFE_TAGS = ["p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "a", "h2", "h3", "h4",
             "blockquote", "span", "small", "hr", "table", "thead", "tbody", "tr", "td", "th", "img"]
SAFE_ATTRS = {"a": ["href", "title", "target", "rel"], "img": ["src", "alt", "loading"], "span": ["class"]}


def safe_html(raw: str) -> str:
    return bleach.clean(raw, tags=SAFE_TAGS, attributes=SAFE_ATTRS, protocols=["http", "https", "mailto"],
                        strip=True)


def safe_url(raw: str) -> str:
    url = (raw or "").strip()
    if url and not (url.startswith("/") or url.startswith("http://") or url.startswith("https://")
                    or url.startswith("mailto:")):
        raise HTTPException(status_code=400, detail=f"'{url[:40]}' isn't a safe link. Use /path or https://…")
    return url[:300]


def page_slug(raw: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in (raw or "").lower())
    while "--" in out:
        out = out.replace("--", "-")
    out = out.strip("-")
    if not out:
        raise HTTPException(status_code=400, detail="Give the page a slug, like about-us.")
    return out


def clean_blocks(blocks: list) -> list:
    out = []
    for b in blocks[:60]:
        kind = str(b.get("type", "text"))
        if kind not in BLOCK_TYPES:
            raise HTTPException(status_code=400,
                                detail=f"Unknown block type '{kind}'. Allowed: {', '.join(BLOCK_TYPES)}.")
        text = str(b.get("text", ""))[:8000]
        if kind in ("richtext", "html", "text", "quote", "cta", "faq"):
            text = safe_html(text)
        out.append({"type": kind, "heading": str(b.get("heading", ""))[:200],
                    "text": text, "image": safe_url(str(b.get("image", ""))),
                    "items": [str(i)[:500] for i in (b.get("items") or [])][:30],
                    "cta_label": str(b.get("cta_label", ""))[:80],
                    "cta_url": safe_url(str(b.get("cta_url", "")))})
    return out


@api.get("/admin/pages")
async def admin_pages(user: dict = Depends(require_perm("content:manage"))):
    docs = await db.cms_pages.find({}).sort("slug", 1).limit(200).to_list(200)
    from scripts.seed_policies import PAGES as POLICY_PAGES
    have = {d["slug"] for d in docs}
    missing = [p["slug"] for p in POLICY_PAGES if p["slug"] not in have]
    return {"items": [clean(d) for d in docs], "block_types": list(BLOCK_TYPES),
            "missing_policy_pages": missing}


@api.post("/admin/pages")
async def create_page(payload: PageIn, user: dict = Depends(require_perm("content:manage"))):
    slug = page_slug(payload.slug)
    if await db.cms_pages.find_one({"slug": slug}):
        raise HTTPException(status_code=400, detail="A page already uses that slug.")
    doc = payload.model_dump() | {"slug": slug, "blocks": clean_blocks(payload.blocks),
                                 "content": safe_html(payload.content)[:20000],
                                 "created_at": iso(now_utc()), "updated_at": iso(now_utc())}
    res = await db.cms_pages.insert_one(doc)
    await audit(user, "page.create", "cms_page", slug, {"title": payload.title})
    return clean(await db.cms_pages.find_one({"_id": res.inserted_id}))


@api.put("/admin/pages/{pid}")
async def update_page(pid: str, payload: PageIn, user: dict = Depends(require_perm("content:manage"))):
    # Admin tooling may address a page by id or by slug.
    page = await db.cms_pages.find_one({"_id": ObjectId(pid)}) if ObjectId.is_valid(pid) else None
    if not page:
        page = await db.cms_pages.find_one({"slug": pid})
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    slug = page_slug(payload.slug)
    clash = await db.cms_pages.find_one({"slug": slug, "_id": {"$ne": page["_id"]}})
    if clash:
        raise HTTPException(status_code=400, detail="Another page already uses that slug.")
    upd = payload.model_dump() | {"slug": slug, "blocks": clean_blocks(payload.blocks),
                                 "content": safe_html(payload.content)[:20000],
                                 "updated_at": iso(now_utc()), "last_updated": iso(now_utc()),
                                 "policy_version": int(page.get("policy_version") or 1) + 1,
                                 "updated_by_name": user.get("full_name", user.get("email", ""))}
    upd.pop("material_change", None)
    # Legal pages keep every past version; nothing is ever overwritten in place.
    await db.cms_page_versions.insert_one({
        "slug": slug, "version": int(page.get("policy_version") or 1), "title": page.get("title", ""),
        "content": page.get("content", ""), "blocks": page.get("blocks", []),
        "seo_title": page.get("seo_title", ""), "seo_description": page.get("seo_description", ""),
        "archived_at": iso(now_utc()), "changed_by": user.get("full_name", user.get("email", ""))})
    await db.cms_pages.update_one({"_id": page["_id"]}, {"$set": upd})
    if payload.material_change and slug in ("terms", "privacy", "guidelines"):
        await db.policy_acceptance_required.update_one(
            {"slug": slug}, {"$set": {"version": upd["policy_version"], "since": iso(now_utc()),
                                      "declared_by": user["id"]}}, upsert=True)
        await audit(user, "POLICY_MATERIAL_CHANGE", "cms_page", slug, {"version": upd["policy_version"]})
    await audit(user, "page.update", "cms_page", slug, {"title": payload.title,
                                                        "version": upd["policy_version"]})
    return clean(await db.cms_pages.find_one({"_id": page["_id"]}))


@api.get("/admin/pages/{slug}/versions")
async def page_versions(slug: str, user: dict = Depends(require_perm("content:manage"))):
    rows = await db.cms_page_versions.find({"slug": slug}).sort("version", -1).to_list(50)
    current = await db.cms_pages.find_one({"slug": slug})
    return {"current": clean(current) if current else None, "items": [clean(r) for r in rows]}


@api.get("/policies/pending")
async def pending_policies(user: dict = Depends(get_current_user)):
    """Which policy updates this member still has to accept."""
    required = await db.policy_acceptance_required.find({}).to_list(20)
    accepted = {a["slug"]: a["version"] for a in
                await db.policy_acceptances.find({"user_id": user["id"]}).to_list(50)}
    pending = []
    for r in required:
        if int(accepted.get(r["slug"], 0)) < int(r["version"]):
            page = await db.cms_pages.find_one({"slug": r["slug"]}, {"title": 1, "slug": 1, "last_updated": 1})
            pending.append({"slug": r["slug"], "version": r["version"],
                            "title": (page or {}).get("title", r["slug"]),
                            "last_updated": (page or {}).get("last_updated", r["since"])})
    return {"items": pending}


@api.post("/policies/accept")
async def accept_policies(request: Request, body: dict = Body(...),
                          user: dict = Depends(get_current_user)):
    slugs = body.get("slugs") or []
    if not slugs:
        raise HTTPException(status_code=400, detail="Nothing to accept.")
    for slug in slugs:
        req = await db.policy_acceptance_required.find_one({"slug": slug})
        version = int((req or {}).get("version") or 1)
        await db.policy_acceptances.insert_one({
            "user_id": user["id"], "email": user["email"], "slug": slug, "version": version,
            "accepted_at": iso(now_utc()), "ip_address": (request.client.host if request.client else ""),
            "user_agent": request.headers.get("user-agent", "")[:300]})
    return {"ok": True, "accepted": slugs}


@api.delete("/admin/pages/{pid}")
async def delete_page(pid: str, user: dict = Depends(require_perm("content:manage"))):
    try:
        page = await db.cms_pages.find_one({"_id": ObjectId(pid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid page id")
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if page["slug"] in HELP_SLUGS:
        raise HTTPException(status_code=400,
                            detail="This page is linked from the app — set it to draft instead of deleting it.")
    await db.cms_pages.delete_one({"_id": page["_id"]})
    await audit(user, "page.delete", "cms_page", page["slug"], {})
    return {"ok": True}


DEFAULT_SITE_CONTENT: dict[str, dict] = {
    "hero": {"tagline": "Your Vibe, Your Buddy",
             "headline": "Great nights out shouldn't",
             "headline_highlight": "depend on who's free.",
             "subtext": "Buddilio is a curated social club for adults, live in 27 cities worldwide. Discover "
                        "parties, dinners, concerts and getaways — then find verified companions who actually "
                        "want to go.",
             "cities_line": "Delhi NCR · Dubai · London · New York · Singapore",
             "image": "", "primary_label": "Explore Events", "primary_url": "/events",
             "secondary_label": "Find Companions", "secondary_url": "/discover"},
    "how_it_works": {"heading": "How Buddilio works",
                     "steps": [{"title": "Pick a night", "text": "Browse curated experiences in your city."},
                               {"title": "Find your buddy", "text": "Match with verified members going too."},
                               {"title": "Show up", "text": "Meet at the venue — our hosts do the introductions."}]},
    "stats": {"heading": "Buddilio in numbers",
              "items": [{"label": "verified members", "value": "12,400+"},
                        {"label": "curated experiences", "value": "380+"},
                        {"label": "cities · 12 countries", "value": "27"}]},
    "testimonials": {"heading": "What members say", "items": []},
    "nav": {"public": [{"label": "Events", "to": "/events"}, {"label": "Organisers", "to": "/hosts"},
                       {"label": "Passes", "to": "/passes"}, {"label": "Membership", "to": "/membership"},
                       {"label": "Journal", "to": "/blog"},
                       {"label": "Safety", "to": "/safety"}],
            "member": [{"label": "Dashboard", "to": "/dashboard"}, {"label": "Discover", "to": "/discover"},
                       {"label": "Events", "to": "/events"}, {"label": "Organisers", "to": "/hosts"},
                       {"label": "Hangouts", "to": "/hangouts"},
                       {"label": "Messages", "to": "/messages"}, {"label": "Membership", "to": "/membership"},
                       {"label": "Orders", "to": "/orders"}, {"label": "Journal", "to": "/blog"},
                       {"label": "Wallet", "to": "/wallet"}]},
    "footer": {"legal_note": ("Buddilio is a social discovery and experience platform for adults aged 21+. "
                              "Buddilio is not a dating or matchmaking platform. User interactions, "
                              "third-party services, events and experiences may involve independent "
                              "individuals or vendors. Please use the platform responsibly and review our "
                              "Safety Centre, Community Guidelines, Terms & Conditions and applicable "
                              "purchase policies before using our services."),
               "groups": [
        {"title": "Buddilio", "links": [{"label": "About Us", "to": "/p/about"},
                                        {"label": "How It Works", "to": "/p/how-it-works"},
                                        {"label": "Journal", "to": "/blog"},
                                        {"label": "FAQ", "to": "/p/faq"},
                                        {"label": "Contact Us", "to": "/p/contact"},
                                        {"label": "Cities We Serve", "to": "/p/cities"}]},
        {"title": "Safety & Trust", "links": [{"label": "Safety Centre", "to": "/safety"},
                                              {"label": "Community Guidelines", "to": "/p/guidelines"},
                                              {"label": "Report a Concern", "to": "/p/report"},
                                              {"label": "Trust & Verification", "to": "/p/trust"}]},
        {"title": "Legal", "links": [{"label": "Privacy Policy", "to": "/p/privacy"},
                                     {"label": "Terms & Conditions", "to": "/p/terms"},
                                     {"label": "Cancellation & Refund Policy", "to": "/p/refund"},
                                     {"label": "Cookie Policy", "to": "/p/cookies"},
                                     {"label": "Vendor Terms", "to": "/p/vendor-terms"}]},
        {"title": "Explore", "links": [{"label": "Events", "to": "/events"},
                                       {"label": "Experiences", "to": "/passes"},
                                       {"label": "Companions", "to": "/discover"},
                                       {"label": "Membership", "to": "/membership"}]}]},
}


async def site_content() -> dict:
    saved = {d["key"]: d.get("data", {}) for d in await db.site_content.find({}).limit(50).to_list(50)}
    return {k: (saved.get(k) or v) for k, v in DEFAULT_SITE_CONTENT.items()} | {
        k: v for k, v in saved.items() if k not in DEFAULT_SITE_CONTENT}


def site_base() -> str:
    return (FRONTEND_URL or "https://buddilio.com").rstrip("/")


def seo_site_base() -> str:
    """Canonicals and sitemaps must name the live domain, never the preview host."""
    base = site_base()
    return "https://buddilio.com" if ("localhost" in base or ".preview." in base) else base


async def _sitemap_urls() -> tuple[list, dict]:
    """Every indexable path — shared by the sitemap and the SEO & indexing panel."""
    urls = [("/", "1.0"), ("/events", "0.9"), ("/passes", "0.8"), ("/membership", "0.8"),
            ("/discover", "0.8"), ("/organisers", "0.7"), ("/safety", "0.7"), ("/blog", "0.9")]
    for post in await db.blog_posts.find({"status": "published"},
                                         {"slug": 1, "updated_at": 1, "category": 1}) \
            .sort("published_at", -1).limit(500).to_list(500):
        urls.append((f"/blog/{post['slug']}", "0.7"))
    for cat in blog.CATEGORIES:
        # matches the URLSearchParams encoding the Journal chips produce, so it stays one canonical URL
        urls.append((f"/blog?category={cat.replace(' ', '+')}", "0.5"))
    pages = await db.cms_pages.find({"status": {"$ne": "draft"}}, {"slug": 1, "last_updated": 1}) \
        .limit(200).to_list(200)
    lastmod = {}
    for pg in pages:
        urls.append((f"/p/{pg['slug']}", "0.6"))
        if pg.get("last_updated"):
            lastmod[f"/p/{pg['slug']}"] = str(pg["last_updated"])[:10]
    for c in await db.cities.find({}, {"name": 1}).limit(300).to_list(300):
        if c.get("name"):
            urls.append((f"/city/{city_slug(c['name'])}", "0.8"))
    for country in COUNTRIES:
        for name in country["cities"]:
            urls.append((f"/city/{city_slug(name)}", "0.8"))
    for ev in await db.events.find({"status": "published"}, {"_id": 1, "updated_at": 1}) \
            .sort("starts_at", -1).limit(500).to_list(500):
        urls.append((f"/events/{ev['_id']}", "0.7"))
    seen, out = set(), []
    for loc, pri in urls:
        if loc in seen:
            continue
        seen.add(loc)
        out.append((loc, pri))
    return out, lastmod


@api.get("/sitemap.xml")
async def sitemap_xml():
    """Dynamic sitemap built from live published content."""
    base = seo_site_url(await seo_settings())
    urls, lastmod = await _sitemap_urls()
    body = []
    for loc, pri in urls:
        mod = f"<lastmod>{lastmod[loc]}</lastmod>" if loc in lastmod else ""
        body.append(f"<url><loc>{base}{xml_escape(loc)}</loc>{mod}<priority>{pri}</priority></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(body) + "</urlset>")
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@api.get("/blog")
async def blog_index(category: str = "", q: str = "", tag: str = "", limit: int = 24, skip: int = 0):
    """Public journal listing — featured post first, then newest."""
    query: dict = {"status": "published"}
    if category:
        query["category"] = category
    if tag:
        query["tags"] = tag
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"title": rx}, {"excerpt": rx}, {"tags": rx}]
    rows = await db.blog_posts.find(query, {"body": 0}).sort("published_at", -1) \
        .skip(max(skip, 0)).limit(min(max(limit, 1), 48)).to_list(48)
    items = [blog.card(clean(r)) for r in rows]
    featured = next((i for i in items if i["featured"]), items[0] if items else None)
    counts = await db.blog_posts.aggregate([{"$match": {"status": "published"}},
                                            {"$group": {"_id": "$category", "n": {"$sum": 1}}}]) \
        .to_list(50)
    return {"items": items, "featured": featured, "total": await db.blog_posts.count_documents(query),
            "categories": [{"name": c["_id"], "count": c["n"]} for c in counts if c["_id"]],
            "all_categories": blog.CATEGORIES}


@api.get("/blog/{slug}")
async def blog_post(slug: str):
    doc = await db.blog_posts.find_one({"slug": slug, "status": "published"})
    if not doc:
        raise HTTPException(status_code=404, detail="That story isn't published.")
    await db.blog_posts.update_one({"_id": doc["_id"]}, {"$inc": {"views": 1}})
    post = clean(doc)
    related = await db.blog_posts.find(
        {"status": "published", "slug": {"$ne": slug},
         "$or": [{"category": post["category"]}, {"tags": {"$in": post.get("tags", [])}}]},
        {"body": 0}).sort("published_at", -1).limit(3).to_list(3)
    if len(related) < 3:
        more = await db.blog_posts.find({"status": "published", "slug": {"$ne": slug}}, {"body": 0}) \
            .sort("published_at", -1).limit(3).to_list(3)
        seen = {r["slug"] for r in related}
        related += [m for m in more if m["slug"] not in seen][:3 - len(related)]
    site = (FRONTEND_URL or "https://buddilio.com").rstrip("/")
    return {"post": post, "related": [blog.card(clean(r)) for r in related],
            "jsonld": blog.article_jsonld(post, site)}


@api.get("/admin/blog")
async def admin_blog_list(user: dict = Depends(require_perm("content:manage"))):
    rows = await db.blog_posts.find({}, {"body": 0}).sort("updated_at", -1).limit(200).to_list(200)
    return {"items": [clean(r) | {"status": r.get("status", "draft")} for r in rows],
            "categories": blog.CATEGORIES}


@api.get("/admin/blog/{post_id}")
async def admin_blog_get(post_id: str, user: dict = Depends(require_perm("content:manage"))):
    doc = await db.blog_posts.find_one({"_id": as_oid(post_id, "post")})
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found.")
    return clean(doc)


@api.post("/admin/blog")
async def admin_blog_create(payload: blog.PostIn, user: dict = Depends(require_perm("content:manage"))):
    doc = blog.to_doc(payload)
    doc["author_name"] = doc["author_name"] or user.get("full_name", "Buddilio Editorial")
    if await db.blog_posts.find_one({"slug": doc["slug"]}):
        doc["slug"] = f"{doc['slug']}-{uuid.uuid4().hex[:4]}"
    res = await db.blog_posts.insert_one(doc)
    await audit(user, "blog.created", "post", str(res.inserted_id), {"title": doc["title"]})
    return {"ok": True, "id": str(res.inserted_id), "slug": doc["slug"]}


@api.put("/admin/blog/{post_id}")
async def admin_blog_update(post_id: str, payload: blog.PostIn,
                            user: dict = Depends(require_perm("content:manage"))):
    existing = await db.blog_posts.find_one({"_id": as_oid(post_id, "post")})
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found.")
    doc = blog.to_doc(payload, existing)
    clash = await db.blog_posts.find_one({"slug": doc["slug"], "_id": {"$ne": existing["_id"]}})
    if clash:
        doc["slug"] = f"{doc['slug']}-{uuid.uuid4().hex[:4]}"
    await db.blog_posts.update_one({"_id": existing["_id"]}, {"$set": doc})
    await audit(user, "blog.updated", "post", post_id, {"title": doc["title"], "status": doc["status"]})
    return {"ok": True, "slug": doc["slug"]}


@api.delete("/admin/blog/{post_id}")
async def admin_blog_delete(post_id: str, user: dict = Depends(require_perm("content:manage"))):
    doc = await db.blog_posts.find_one({"_id": as_oid(post_id, "post")})
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found.")
    await db.blog_posts.delete_one({"_id": doc["_id"]})
    await audit(user, "blog.deleted", "post", post_id, {"title": doc.get("title", "")})
    return {"ok": True}


@api.post("/admin/cms/seed-policies")
async def seed_policy_pages(mode: str = "missing", user: dict = Depends(require_perm("content:manage"))):
    """Fills the standard policy/information pages. mode=missing never touches existing pages."""
    from scripts.seed_policies import seed as seed_pages
    res = await seed_pages(db, only_missing=(mode != "all"))
    await audit(user, "CMS_POLICIES_SEEDED", "cms_page", "", res)
    return res


@api.get("/site-content")
async def get_site_content():
    """Everything the marketing surfaces render, editable from the admin."""
    pages = await db.cms_pages.find({"status": {"$ne": "draft"}},
                                    {"slug": 1, "title": 1, "nav_header": 1, "nav_footer_group": 1,
                                     "nav_label": 1, "order": 1}).limit(200).to_list(200)
    content = await site_content()
    content["pages"] = [{"slug": p["slug"], "title": p.get("title", p["slug"]),
                         "label": p.get("nav_label") or p.get("title", p["slug"]),
                         "header": bool(p.get("nav_header")), "footer_group": p.get("nav_footer_group", ""),
                         "order": p.get("order", 0)} for p in pages]
    return content


@api.get("/admin/site-content")
async def admin_site_content(user: dict = Depends(require_perm("content:manage"))):
    return {"content": await site_content(), "defaults": DEFAULT_SITE_CONTENT}


@api.put("/admin/site-content/{key}")
async def update_site_content(key: str, body: dict, user: dict = Depends(require_perm("content:manage"))):
    if key not in DEFAULT_SITE_CONTENT:
        raise HTTPException(status_code=400, detail="Unknown content section.")
    data = body.get("data", body)
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Section content must be an object.")
    await db.site_content.update_one({"key": key},
                                     {"$set": {"data": data, "updated_at": iso(now_utc())}}, upsert=True)
    await audit(user, "site_content.update", "site_content", key, {})
    return {"ok": True, "key": key, "data": data}


@api.delete("/admin/site-content/{key}")
async def reset_site_content(key: str, user: dict = Depends(require_perm("content:manage"))):
    if key not in DEFAULT_SITE_CONTENT:
        raise HTTPException(status_code=400, detail="Unknown content section.")
    await db.site_content.delete_one({"key": key})
    await audit(user, "site_content.reset", "site_content", key, {})
    return {"ok": True, "data": DEFAULT_SITE_CONTENT[key]}


# ---- profiles: create, edit, delete ----
PROFILE_EDITABLE = ("full_name", "email", "city", "country", "age", "bio", "photo", "mobile", "website",
                    "interests", "event_categories", "lifestyle", "org_name", "role", "status", "verified",
                    "email_verified", "documents", "staff_role", "extra_permissions")


class AdminProfileIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    full_name: str
    email: EmailStr
    role: str = "user"                    # user | partner | manager | admin
    password: str = ""
    city: str = ""
    country: str = ""
    age: int = 25
    bio: str = ""
    photo: str = ""
    mobile: str = ""
    org_name: str = ""
    interests: List[str] = []
    event_categories: List[str] = []
    status: str = "active"
    verified: bool = False


@api.post("/admin/users")
async def admin_create_user(payload: AdminProfileIn, user: dict = Depends(require_perm("members:manage"))):
    if payload.role not in ("user", "partner", "manager", "admin"):
        raise HTTPException(status_code=400, detail="Role must be user, partner, manager or admin.")
    if payload.role in ("admin", "manager") and "team:manage" not in perms_of(user):
        raise HTTPException(status_code=403, detail="Only the team admin can create staff accounts.")
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Someone already uses that email on Buddilio.")
    if payload.age < 21:
        raise HTTPException(status_code=400, detail="Buddilio is 21+.")
    temp = payload.password or secrets.token_urlsafe(14)
    doc = {k: v for k, v in payload.model_dump().items() if k != "password"}
    doc.update({"email": email, "password_hash": hash_password(temp), "blocked": [], "connections": [],
                "saved_events": [], "email_verified": False, "created_by": user["id"],
                "created_at": iso(now_utc())})
    res = await db.users.insert_one(doc)
    if not payload.password:
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "token": token, "user_id": str(res.inserted_id),
            "expires_at": now_utc() + timedelta(days=7), "created_at": iso(now_utc())})
        await send_tpl("account_created", email, {
            "first_name": first_name(payload.full_name),
            "reset_url": f"{FRONTEND_URL}/reset-password?token={token}"})
    await audit(user, "profile.create", "user", str(res.inserted_id), {"email": email, "role": payload.role})
    return clean(await db.users.find_one({"_id": res.inserted_id}))


@api.put("/admin/users/{uid}")
async def admin_edit_profile(uid: str, body: dict, user: dict = Depends(require_perm("members:manage"))):
    """Full profile edit — every field the member could set, plus the staff-only ones."""
    try:
        target = await db.users.find_one({"_id": ObjectId(uid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid profile id")
    if not target:
        raise HTTPException(status_code=404, detail="Profile not found")
    upd = {k: v for k, v in body.items() if k in PROFILE_EDITABLE}
    reject_masked(upd.get("email", ""))
    reject_masked(upd.get("mobile", ""), "phone number")
    if isinstance(upd.get("bio"), str):
        upd["bio"] = safe_html(upd["bio"])[:4000]
    if not upd:
        raise HTTPException(status_code=400, detail="Nothing to change.")
    if ("staff_role" in upd or "extra_permissions" in upd or upd.get("role") in ("admin", "manager")) \
            and "team:manage" not in perms_of(user):
        raise HTTPException(status_code=403, detail="Only the team admin can change staff access.")
    if "role" in upd and target.get("role") in ("admin", "manager") and "team:manage" not in perms_of(user):
        raise HTTPException(status_code=403, detail="Only the team admin can change a staff member's role.")
    if target.get("role") in ("admin", "manager") and "team:manage" not in perms_of(user):
        raise HTTPException(status_code=403, detail="Only the team admin can edit staff accounts.")
    if "email" in upd:
        upd["email"] = str(upd["email"]).lower().strip()
        if await db.users.find_one({"email": upd["email"], "_id": {"$ne": target["_id"]}}):
            raise HTTPException(status_code=400, detail="Another account already uses that email.")
    if body.get("password"):
        upd["password_hash"] = hash_password(str(body["password"]))
    await db.users.update_one({"_id": target["_id"]}, {"$set": upd})
    await audit(user, "profile.update", "user", uid, {k: v for k, v in upd.items() if k != "password_hash"})
    return clean(await db.users.find_one({"_id": target["_id"]}))


@api.delete("/admin/users/{uid}")
async def admin_delete_profile(uid: str, mode: str = "soft", user: dict = Depends(require_perm("members:manage"))):
    """Soft delete disables the account and keeps the history; hard delete removes the person entirely."""
    if mode not in ("soft", "hard"):
        raise HTTPException(status_code=400, detail="Mode must be soft or hard.")
    if uid == user["id"]:
        raise HTTPException(status_code=400, detail="You can't delete your own account.")
    try:
        target = await db.users.find_one({"_id": ObjectId(uid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid profile id")
    if not target:
        raise HTTPException(status_code=404, detail="Profile not found")
    if target.get("role") in ("admin", "manager") and "team:manage" not in perms_of(user):
        raise HTTPException(status_code=403, detail="Only the team admin can remove staff accounts.")
    if mode == "soft":
        await db.users.update_one({"_id": target["_id"]},
                                  {"$set": {"status": "deleted", "deleted_at": iso(now_utc())}})
        await audit(user, "profile.soft_delete", "user", uid, {"email": target.get("email")})
        return {"ok": True, "mode": "soft", "status": "deleted"}
    if target.get("role") == "partner" and await db.events.count_documents({"partner_id": uid}):
        raise HTTPException(status_code=400,
                            detail="This organiser still has events. Move or delete those first, or use soft delete.")
    await db.event_participants.delete_many({"user_id": uid})
    await db.host_follows.delete_many({"user_id": uid})
    await db.event_photos.delete_many({"user_id": uid})
    await db.reviews.delete_many({"user_id": uid})
    await db.notifications.delete_many({"user_id": uid})
    await db.push_subscriptions.delete_many({"user_id": uid})
    await db.users.delete_one({"_id": target["_id"]})
    await audit(user, "profile.hard_delete", "user", uid, {"email": target.get("email")})
    return {"ok": True, "mode": "hard"}


@api.post("/admin/users/{uid}/restore")
async def admin_restore_profile(uid: str, user: dict = Depends(require_perm("members:manage"))):
    res = await db.users.update_one({"_id": ObjectId(uid), "status": "deleted"},
                                   {"$set": {"status": "active"}, "$unset": {"deleted_at": ""}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="No deleted profile with that id.")
    await audit(user, "profile.restore", "user", uid, {})
    return {"ok": True, "status": "active"}


# ---- events: admins can build and remove them too ----
class AdminEventIn(EventIn):
    partner_id: str = ""
    status: str = "published"


@api.post("/admin/events")
async def admin_create_event(payload: AdminEventIn, user: dict = Depends(require_perm("events:moderate"))):
    if payload.status not in ("draft", "submitted", "published", "rejected", "completed"):
        raise HTTPException(status_code=400, detail="Unknown event status.")
    host = None
    if payload.partner_id:
        host = await db.users.find_one({"_id": ObjectId(payload.partner_id), "role": "partner"})
        if not host:
            raise HTTPException(status_code=400, detail="Pick an existing organiser for this event.")
    doc = await price_event(with_country(payload.model_dump(exclude={"partner_id", "status"})))
    doc.update({"partner_id": payload.partner_id or "",
                "partner_name": (host.get("org_name") or host.get("full_name")) if host else "Buddilio",
                "status": payload.status, "participant_count": 0, "created_at": iso(now_utc())})
    res = await db.events.insert_one(doc)
    await audit(user, "event.admin_create", "event", str(res.inserted_id), {"title": payload.title})
    return clean(await db.events.find_one({"_id": res.inserted_id}))


@api.put("/admin/events/{eid}")
async def admin_edit_event(eid: str, payload: AdminEventIn, user: dict = Depends(require_perm("events:moderate"))):
    try:
        ev = await db.events.find_one({"_id": ObjectId(eid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event id")
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    upd = await price_event(with_country(payload.model_dump(exclude={"partner_id"})))
    if payload.partner_id and payload.partner_id != ev.get("partner_id"):
        host = await db.users.find_one({"_id": ObjectId(payload.partner_id), "role": "partner"})
        if not host:
            raise HTTPException(status_code=400, detail="Pick an existing organiser for this event.")
        upd["partner_id"] = payload.partner_id
        upd["partner_name"] = host.get("org_name") or host.get("full_name")
    await db.events.update_one({"_id": ev["_id"]}, {"$set": upd})
    await audit(user, "event.admin_update", "event", eid, {"title": payload.title})
    return clean(await db.events.find_one({"_id": ev["_id"]}))


@api.delete("/admin/events/{eid}")
async def admin_delete_event(eid: str, force: bool = False, user: dict = Depends(require_perm("events:moderate"))):
    try:
        ev = await db.events.find_one({"_id": ObjectId(eid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event id")
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    going = await db.event_participants.count_documents({"event_id": eid, "status": "confirmed"})
    paid = await db.orders.count_documents({"event_id": eid, "status": "paid"})
    if paid:
        raise HTTPException(status_code=400,
                            detail=f"{paid} paid order(s) exist for this event. Refund them first, "
                                   "then delete it.")
    if going and not force:
        raise HTTPException(status_code=400,
                            detail=f"{going} people are confirmed for this event. Cancel it or pass force=true.")
    await db.event_participants.delete_many({"event_id": eid})
    await db.event_photos.delete_many({"event_id": eid})
    await db.events.delete_one({"_id": ev["_id"]})
    await audit(user, "event.delete", "event", eid, {"title": ev.get("title"), "confirmed": going})
    return {"ok": True, "removed_participants": going}


# ---- editorial city guides ----
@api.get("/admin/city-guides")
async def admin_city_guides(user: dict = Depends(require_perm("content:manage"))):
    saved = {d["slug"]: d.get("data", {}) for d in await db.city_guides.find({}).limit(200).to_list(200)}
    cities = [(c, country["name"]) for country in COUNTRIES for c in country["cities"]]
    return {"items": [{"city": c, "slug": city_slug(c),
                       "guide": saved.get(city_slug(c)) or guide_for(c) or auto_guide(c, cn),
                       "custom": city_slug(c) in saved,
                       "auto": city_slug(c) not in saved and not guide_for(c)} for c, cn in cities]}


@api.put("/admin/city-guides/{slug}")
async def update_city_guide(slug: str, body: dict, user: dict = Depends(require_perm("content:manage"))):
    city, _ = find_city(slug)
    data = body.get("guide", body)
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Guide content must be an object.")
    await db.city_guides.update_one({"slug": slug},
                                   {"$set": {"city": city, "data": data, "updated_at": iso(now_utc())}},
                                   upsert=True)
    await audit(user, "city_guide.update", "city", slug, {})
    return {"ok": True, "slug": slug, "guide": data}


@api.delete("/admin/city-guides/{slug}")
async def reset_city_guide(slug: str, user: dict = Depends(require_perm("content:manage"))):
    city, _ = find_city(slug)
    await db.city_guides.delete_one({"slug": slug})
    await audit(user, "city_guide.reset", "city", slug, {})
    country = country_for_city(city) or {}
    return {"ok": True, "guide": guide_for(city) or auto_guide(city, country.get("name", ""))}


async def city_guide(city: str) -> dict:
    saved = await db.city_guides.find_one({"slug": city_slug(city)})
    country = country_for_city(city) or {}
    return (saved or {}).get("data") or guide_for(city) or auto_guide(city, country.get("name", ""))


# ---------------- paid companion hangouts (premium only) ----------------
# Time and company only. Rates are per hour, Buddilio keeps COMPANION_CUT%, the rest is the companion's.
COMPANION_CUT = float(os.environ.get("COMPANION_CUT_PERCENT", "25"))
HANGOUT_TERMS = ("Hangouts are for company and conversation only — a meal, an event, a walk around town. "
                 "Anything else is off-limits and gets both accounts removed. Meet in public venues. "
                 "Payments are final and non-refundable; if your companion declines or doesn't show, "
                 "you get Buddilio credit instead.")
HANGOUT_FEE_DEFAULT = float(os.environ.get("HANGOUT_REQUEST_FEE", "100"))
BOOKING_OPEN = ("pending_request_fee", "pending_payment", "awaiting_acceptance",
                "payment_due", "counter_offered", "confirmed")
BOOKING_IN_FLIGHT = ("pending_request_fee", "pending_payment", "awaiting_acceptance",
                     "payment_due", "counter_offered")


async def request_fee() -> float:
    """Small non-refundable fee charged on every request so companions aren't spammed."""
    s = await db.settings.find_one({}, {"hangout_request_fee": 1}) or {}
    try:
        fee = float(s.get("hangout_request_fee"))
    except (TypeError, ValueError):
        fee = HANGOUT_FEE_DEFAULT
    return round(max(fee, 0), 2)


def booking_refundable(b: dict) -> float:
    """Everything the guest paid apart from the request fee, which is never returned."""
    return round(float(b.get("paid_total") or 0) - float(b.get("fee_paid") or 0), 2)


async def premium_member(user: dict = Depends(get_current_user)) -> dict:
    """Hangouts are invisible to everyone but plans that switch hangout access on."""
    member = await membership_active(user["id"])
    if not member:
        raise HTTPException(status_code=403, detail="Hangouts are a premium member feature.")
    s = await db.settings.find_one({}, {"companions_min_plan": 1}) or {}
    required = (s.get("companions_min_plan") or "").strip()
    if required and member.get("plan_name") != required:
        raise HTTPException(status_code=403, detail=f"Hangouts are for {required} members.")
    plan = None
    if member.get("plan_id"):
        try:
            plan = await db.membership_plans.find_one({"_id": ObjectId(member["plan_id"])},
                                                     {"hangouts_access": 1, "name": 1})
        except Exception:
            plan = None
    # Plans created before this switch existed have no flag at all, so they keep their old access.
    if plan and "hangouts_access" in plan and not plan.get("hangouts_access"):
        raise HTTPException(status_code=403,
                            detail=f"Hangouts aren't included in {plan.get('name', 'your plan')}. "
                                   "Upgrade to unlock paid hangouts.")
    user["membership"] = member
    return user


class CompanionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    hourly_rate: float = Field(gt=0)
    min_hours: int = Field(default=1, ge=1, le=6)
    max_hours: int = Field(default=4, ge=1, le=6)
    headline: str = ""
    about: str = ""
    city: str = ""
    languages: List[str] = []
    packages: List[dict] = []          # [{label, hours, price}]
    enabled: bool = True
    accept_terms: bool = False


def companion_card(u: dict, mine: bool = False) -> dict:
    c = u.get("companion") or {}
    out = {"id": str(u["_id"]), "name": short_name(u.get("full_name", "Member")),
           "photo": u.get("photo", ""), "city": c.get("city") or u.get("city", ""),
           "age": u.get("age", 0), "headline": c.get("headline", ""), "about": c.get("about", ""),
           "languages": c.get("languages", []), "hourly_rate": c.get("hourly_rate", 0),
           "min_hours": c.get("min_hours", 1), "max_hours": c.get("max_hours", 4),
           "packages": c.get("packages", []), "currency": BASE_CURRENCY,
           "status": c.get("status", "none"), "enabled": bool(c.get("enabled")),
           "hangouts": c.get("completed", 0), "rating": c.get("rating", 0),
           "rating_count": c.get("rating_count", 0), "verified": bool(u.get("verified"))}
    if mine:
        out |= {"full_name": u.get("full_name", ""), "rejected_reason": c.get("rejected_reason", ""),
                "cut_percent": COMPANION_CUT, "terms": HANGOUT_TERMS}
    else:
        # Rates stay private until the companion accepts the request.
        out |= {"hourly_rate": 0, "rate_hidden": True,
                "packages": [{"label": p.get("label", ""), "hours": p.get("hours", 0)}
                             for p in (c.get("packages") or [])]}
    return out


def clean_packages(rows: list) -> list:
    out = []
    for r in rows[:6]:
        hours = int(r.get("hours") or 0)
        price = round(float(r.get("price") or 0), 2)
        if hours < 1 or hours > 6 or price <= 0:
            raise HTTPException(status_code=400, detail="Each package needs 1-6 hours and a price above zero.")
        out.append({"label": str(r.get("label", ""))[:60] or f"{hours} hours", "hours": hours, "price": price})
    return out


@api.get("/me/companion")
async def my_companion_profile(user: dict = Depends(get_current_user)):
    doc = await db.users.find_one({"_id": ObjectId(user["id"])})
    return {"profile": companion_card(doc, mine=True), "terms": HANGOUT_TERMS,
            "cut_percent": COMPANION_CUT, "can_apply": bool(doc.get("verified"))}


@api.post("/me/companion")
async def apply_as_companion(payload: CompanionIn, user: dict = Depends(get_current_user)):
    """Anyone verified can switch this on and name their rate — an admin approves before they're listed."""
    doc = await db.users.find_one({"_id": ObjectId(user["id"])})
    if doc.get("role") != "user":
        raise HTTPException(status_code=403, detail="Only members can offer hangouts.")
    if not doc.get("verified"):
        raise HTTPException(status_code=403, detail="Get your profile verified first, then you can offer hangouts.")
    if not payload.accept_terms:
        raise HTTPException(status_code=400, detail="Please accept the hangout terms to continue.")
    if payload.max_hours < payload.min_hours:
        raise HTTPException(status_code=400, detail="Maximum hours can't be less than the minimum.")
    existing = doc.get("companion") or {}
    status = existing.get("status") if existing.get("status") == "approved" else "pending"
    c = {"hourly_rate": round(payload.hourly_rate, 2), "min_hours": payload.min_hours,
         "max_hours": payload.max_hours, "headline": payload.headline[:120],
         "about": safe_html(payload.about)[:4000], "city": payload.city or doc.get("city", ""),
         "languages": [l[:30] for l in payload.languages][:6],
         "packages": clean_packages(payload.packages), "enabled": payload.enabled,
         "status": status, "completed": existing.get("completed", 0),
         "accepted_terms_at": iso(now_utc()),
         "applied_at": existing.get("applied_at") or iso(now_utc())}
    await db.users.update_one({"_id": doc["_id"]}, {"$set": {"companion": c}})
    if status == "pending":
        await notify(user["id"], "Hangout profile submitted",
                     "Our team reviews new hangout hosts within a business day. We'll tell you the moment "
                     "you're live.", "system", "/hangouts/host", email=False)
    return companion_card(await db.users.find_one({"_id": doc["_id"]}), mine=True)


@api.get("/companions")
async def list_companions(q: str = "", city: str = "", max_rate: float = -1,
                          sort: Literal["rate", "rate_desc", "rating", "experience"] = "rate",
                          page: int = 1, limit: int = 12,
                          user: dict = Depends(premium_member)):
    flt: dict[str, Any] = {"role": "user", "status": "active", "verified": True,
                           "companion.status": "approved", "companion.enabled": True,
                           "_id": {"$ne": ObjectId(user["id"])}}
    if city:
        flt["companion.city"] = city
    if max_rate >= 0:
        flt["companion.hourly_rate"] = {"$lte": max_rate}
    if q:
        flt["$or"] = [{"full_name": {"$regex": q, "$options": "i"}},
                      {"companion.headline": {"$regex": q, "$options": "i"}}]
    total = await db.users.count_documents(flt)
    order = {"rating": [("companion.rating", -1), ("companion.completed", -1)],
             "experience": [("companion.completed", -1), ("companion.rating", -1)],
             "rate_desc": [("companion.hourly_rate", -1)]}.get(sort, [("companion.hourly_rate", 1)])
    docs = await db.users.find(flt, {"full_name": 1, "photo": 1, "city": 1, "age": 1, "companion": 1,
                                     "verified": 1}).sort(order) \
        .skip((page - 1) * limit).limit(limit).to_list(limit)
    return {"items": [companion_card(d) for d in docs], "total": total, "page": page,
            "terms": HANGOUT_TERMS, "currency": BASE_CURRENCY, "request_fee": await request_fee(),
            "free_requests_left": await free_requests_left(user["id"], user.get("membership"))}


@api.get("/companions/{cid}")
async def get_companion(cid: str, user: dict = Depends(premium_member)):
    try:
        doc = await db.users.find_one({"_id": ObjectId(cid), "companion.status": "approved",
                                      "companion.enabled": True})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid companion id")
    if not doc:
        raise HTTPException(status_code=404, detail="This companion isn't available right now.")
    return companion_card(doc) | {"terms": HANGOUT_TERMS, "request_fee": await request_fee(),
                                  "free_requests_left": await free_requests_left(user["id"],
                                                                                 user.get("membership"))}


class BookingIn(BaseModel):
    hours: int = Field(default=0, ge=0, le=6)
    package_index: int = -1
    offer_amount: float = 0            # member can offer above the listed rate
    starts_at: str
    place: str = ""
    note: str = ""
    accept_terms: bool = False


def booking_view(b: dict, me: str, names: dict) -> dict:
    other = b["companion_id"] if b["member_id"] == me else b["member_id"]
    hidden = b["member_id"] == me and b["status"] in ("pending_request_fee", "awaiting_acceptance")
    return {"id": str(b["_id"]), "role": "member" if b["member_id"] == me else "companion",
            "member_id": b["member_id"], "companion_id": b["companion_id"],
            "with_name": names.get(other, "Member"), "with_photo": (names.get(other + ":photo") or ""),
            "rate_hidden": hidden, "request_fee": b.get("request_fee", 0),
            "fee_paid": b.get("fee_paid", 0),
            "hours": b["hours"], "amount": 0 if hidden else b["amount"], "paid_total": b.get("paid_total", 0),
            "due_amount": b.get("due_amount", 0), "counter_amount": b.get("counter_amount", 0),
            "counter_note": b.get("counter_note", ""), "currency": b.get("currency", BASE_CURRENCY),
            "cut_percent": b.get("cut_percent", COMPANION_CUT),
            "companion_net": b.get("companion_net", 0), "status": b["status"],
            "starts_at": b["starts_at"], "place": b.get("place", ""), "note": b.get("note", ""),
            "package": b.get("package", ""), "order_id": b.get("order_id", ""),
            "rated": bool(b.get("rated")), "fee_waived": bool(b.get("fee_waived")),
            "created_at": b.get("created_at", "")}


async def booking_names(rows: list) -> dict:
    ids = {r["member_id"] for r in rows} | {r["companion_id"] for r in rows}
    docs = await load_many(db.users, list(ids), {"full_name": 1, "photo": 1})
    out = {}
    for uid, d in docs.items():
        out[uid] = short_name(d.get("full_name", "Member"))
        out[uid + ":photo"] = d.get("photo", "")
    return out


@api.post("/companions/{cid}/bookings")
async def create_booking(cid: str, payload: BookingIn, user: dict = Depends(premium_member)):
    if not payload.accept_terms:
        raise HTTPException(status_code=400, detail="Please accept the hangout terms to book.")
    if cid == user["id"]:
        raise HTTPException(status_code=400, detail="You can't book yourself.")
    doc = await db.users.find_one({"_id": ObjectId(cid), "companion.status": "approved",
                                  "companion.enabled": True})
    if not doc:
        raise HTTPException(status_code=404, detail="This companion isn't available right now.")
    c = doc["companion"]
    try:
        starts = datetime.fromisoformat(payload.starts_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Pick a valid date and time.")
    if starts <= now_utc() + timedelta(hours=2):
        raise HTTPException(status_code=400, detail="Book at least two hours ahead.")
    label = ""
    if payload.package_index >= 0:
        packs = c.get("packages") or []
        if payload.package_index >= len(packs):
            raise HTTPException(status_code=400, detail="That package is no longer offered.")
        pack = packs[payload.package_index]
        hours, listed, label = pack["hours"], round(float(pack["price"]), 2), pack.get("label", "")
    else:
        hours = payload.hours or c.get("min_hours", 1)
        if hours < c.get("min_hours", 1) or hours > c.get("max_hours", 4):
            raise HTTPException(status_code=400,
                                detail=f"This companion takes bookings of {c.get('min_hours', 1)}-"
                                       f"{c.get('max_hours', 4)} hours.")
        listed = round(float(c["hourly_rate"]) * hours, 2)
    offer = round(float(payload.offer_amount or 0), 2)
    if offer > listed * 3:
        raise HTTPException(status_code=400,
                            detail="An offer can't be more than three times the listed price.")
    amount = max(listed, offer)
    if await db.companion_bookings.count_documents(
            {"member_id": user["id"], "companion_id": cid, "status": {"$in": list(BOOKING_IN_FLIGHT)}}):
        raise HTTPException(status_code=400,
                            detail="You already have a request waiting with this companion — "
                                   "finish that one first.")
    fee = await request_fee()
    waived = False
    if fee > 0 and await free_requests_left(user["id"], user.get("membership")) > 0:
        fee, waived = 0.0, True
    doc_b = {"member_id": user["id"], "companion_id": cid, "hours": hours, "package": label,
             "listed_amount": listed, "amount": amount, "due_amount": fee, "paid_total": 0.0,
             "request_fee": fee, "fee_paid": 0.0, "fee_waived": waived,
             "cut_percent": COMPANION_CUT, "currency": BASE_CURRENCY,
             "status": "awaiting_acceptance" if waived else "pending_request_fee",
             "starts_at": iso(starts), "place": payload.place[:160], "note": payload.note[:500],
             "item_name": f"Hangout request fee · {short_name(doc.get('full_name', 'a companion'))}",
             "created_at": iso(now_utc())}
    res = await db.companion_bookings.insert_one(doc_b)
    b = await db.companion_bookings.find_one({"_id": res.inserted_id})
    names = await booking_names([b])
    if waived:
        await notify(cid, "New hangout request",
                     f"{short_name(user.get('full_name', 'A member'))} requested {hours}h on "
                     f"{iso(starts)[:10]}. Accept with your price, counter or decline.",
                     "order", "/hangouts/host")
        return {"booking": booking_view(b, user["id"], names), "next": "sent", "request_fee": 0,
                "fee_waived": True,
                "free_requests_left": await free_requests_left(user["id"], user.get("membership"))}
    return {"booking": booking_view(b, user["id"], names), "next": "checkout",
            "request_fee": fee, "fee_waived": False,
            "checkout": {"kind": "companion", "item_id": str(res.inserted_id), "amount": fee}}


async def fulfil_companion(order: dict, uid: str):
    """Money is in. Either it's the request fee, or the agreed price after the companion said yes."""
    b = await db.companion_bookings.find_one({"_id": ObjectId(order["ref_id"])})
    if not b or b["member_id"] != uid:
        return
    paid = round(float(b.get("paid_total") or 0) + float(order["total"]), 2)
    if b["status"] == "pending_request_fee":
        # Store what the guest was actually charged (fee + tax) — none of it comes back.
        await db.companion_bookings.update_one({"_id": b["_id"]}, {"$set": {
            "status": "awaiting_acceptance", "paid_total": paid, "fee_paid": paid, "due_amount": 0,
            "fee_order_id": str(order["_id"]), "requested_at": iso(now_utc())}})
        member = await db.users.find_one({"_id": ObjectId(uid)}, {"full_name": 1})
        await notify(b["companion_id"], "New paid hangout request",
                     f"{short_name((member or {}).get('full_name', 'A member'))} requested "
                     f"{b['hours']}h on {b['starts_at'][:10]}. Accept with your price, counter or decline.",
                     "order", "/hangouts/host")
        return
    # The agreed price drives the split; any Buddilio credit the guest spent is our marketing cost.
    agreed = round(float(b.get("counter_amount") or b["amount"]), 2)
    await confirm_booking(b, agreed, paid, str(order["_id"]))


async def confirm_booking(b: dict, agreed: float, paid: float, order_id: str):
    cut = round(agreed * b.get("cut_percent", COMPANION_CUT) / 100, 2)
    await db.companion_bookings.update_one({"_id": b["_id"]}, {"$set": {
        "status": "confirmed", "paid_total": paid, "due_amount": 0,
        "amount": agreed, "companion_net": round(agreed - cut, 2), "platform_fee": cut,
        "order_id": order_id, "confirmed_at": iso(now_utc())}})
    await companion_payout(await db.companion_bookings.find_one({"_id": b["_id"]}))
    await notify(b["companion_id"], "Hangout confirmed",
                 "Your guest paid the agreed amount. The booking is locked in.",
                 "order", "/hangouts/host")
    await notify(b["member_id"], "Your hangout is confirmed",
                 f"You're set for {b['hours']}h on {b['starts_at'][:10]}. Meet in a public venue.",
                 "order", "/hangouts/bookings")


async def companion_payout(b: dict):
    """75% (or whatever the cut leaves) goes to the companion's payout ledger, same place organisers are paid."""
    if await db.payouts.find_one({"booking_id": str(b["_id"])}):
        return
    await db.payouts.insert_one({
        "partner_id": b["companion_id"], "booking_id": str(b["_id"]), "kind": "companion",
        "event_id": "", "event_title": f"Hangout · {b['hours']}h on {b['starts_at'][:10]}",
        "orders": 1, "gross": b["amount"],
        "fee_percent": b.get("cut_percent", COMPANION_CUT), "fee": b.get("platform_fee", 0),
        "net": b.get("companion_net", 0), "currency": b.get("currency", BASE_CURRENCY),
        "status": "pending", "created_at": iso(now_utc())})


async def grant_credit(user_id: str, amount: float, reason: str, booking_id: str = "") -> float:
    if amount <= 0:
        return 0.0
    await db.credits.insert_one({"user_id": user_id, "amount": round(amount, 2), "type": "grant",
                                 "reason": reason, "booking_id": booking_id,
                                 "created_at": iso(now_utc())})
    await notify(user_id, f"{fmt_money(amount)} Buddilio credit added", reason, "refund", "/orders")
    return round(amount, 2)


# ---------------- wallet: top-ups, saved card, free requests ----------------
WALLET_MIN, WALLET_MAX = 500.0, 200000.0


class TopUpIn(BaseModel):
    amount: float = Field(gt=0)


class CardIn(BaseModel):
    name: str
    number: str
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=2026, le=2099)
    autopay: bool = True


def card_view(u: dict) -> Optional[dict]:
    c = u.get("saved_card")
    return {"brand": c["brand"], "last4": c["last4"], "name": c["name"],
            "expiry": f"{c['exp_month']:02d}/{str(c['exp_year'])[-2:]}",
            "autopay": bool(c.get("autopay", True))} if c else None


async def free_requests_left(user_id: str, member: Optional[dict]) -> int:
    """Paying members get a few fee-free hangout requests every calendar month."""
    if not member:
        return 0
    s = await db.settings.find_one({}, {"hangout_free_requests": 1}) or {}
    try:
        quota = int(s.get("hangout_free_requests", 3))
    except (TypeError, ValueError):
        quota = 3
    if quota <= 0:
        return 0
    month_start = now_utc().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = await db.companion_bookings.count_documents(
        {"member_id": user_id, "fee_waived": True, "created_at": {"$gte": iso(month_start)}})
    return max(quota - used, 0)


@api.get("/wallet")
async def my_wallet(user: dict = Depends(get_current_user)):
    doc = await db.users.find_one({"_id": ObjectId(user["id"])}, {"saved_card": 1, "auto_reload": 1})
    rows = await db.credits.find({"user_id": user["id"]}).sort("created_at", -1).limit(30).to_list(30)
    member = await membership_active(user["id"])
    return {"balance": await credit_balance(user["id"]),
            "entries": [{"amount": r["amount"], "reason": r.get("reason", ""), "type": r.get("type", ""),
                         "created_at": r.get("created_at", "")} for r in rows],
            "card": card_view(doc or {}), "min_topup": WALLET_MIN, "max_topup": WALLET_MAX,
            "auto_reload": (doc or {}).get("auto_reload") or {"enabled": False, "threshold": 500,
                                                             "amount": 1000},
            "free_requests_left": await free_requests_left(user["id"], member)}


@api.post("/wallet/topup")
async def start_topup(payload: TopUpIn, user: dict = Depends(get_current_user)):
    amount = round(float(payload.amount), 2)
    if amount < WALLET_MIN or amount > WALLET_MAX:
        raise HTTPException(status_code=400,
                            detail=f"Top up between {fmt_money(WALLET_MIN)} and {fmt_money(WALLET_MAX)}.")
    res = await db.wallet_topups.insert_one({"user_id": user["id"], "amount": amount, "status": "pending",
                                            "created_at": iso(now_utc())})
    return {"topup_id": str(res.inserted_id),
            "checkout": {"kind": "wallet", "item_id": str(res.inserted_id), "amount": amount}}


async def fulfil_topup(order: dict, uid: str):
    t = await db.wallet_topups.find_one({"_id": ObjectId(order["ref_id"])})
    if not t or t["user_id"] != uid or t.get("status") == "paid":
        return
    await db.wallet_topups.update_one({"_id": t["_id"]}, {"$set": {
        "status": "paid", "order_id": str(order["_id"]), "paid_at": iso(now_utc())}})
    await grant_credit(uid, float(t["amount"]), "Wallet top-up", "")


@api.put("/wallet/card")
async def save_card(payload: CardIn, user: dict = Depends(get_current_user)):
    """SIMULATED card vault — we keep the last four digits only, never the full number."""
    digits = re.sub(r"\D", "", payload.number)
    if len(digits) < 13 or len(digits) > 19:
        raise HTTPException(status_code=400, detail="Enter a valid card number.")
    brand = {"4": "Visa", "5": "Mastercard", "6": "RuPay", "3": "Amex"}.get(digits[0], "Card")
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"saved_card": {
        "brand": brand, "last4": digits[-4:], "name": payload.name[:60],
        "exp_month": payload.exp_month, "exp_year": payload.exp_year,
        "autopay": payload.autopay, "saved_at": iso(now_utc())}}})
    doc = await db.users.find_one({"_id": ObjectId(user["id"])}, {"saved_card": 1})
    return {"ok": True, "card": card_view(doc)}


@api.delete("/wallet/card")
async def remove_card(user: dict = Depends(get_current_user)):
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$unset": {"saved_card": ""}})
    return {"ok": True, "card": None}


async def charge_saved_card(b: dict, amount: float) -> Optional[dict]:
    """SIMULATED off-session charge on the guest's saved card, mirroring a gateway capture."""
    u = await db.users.find_one({"_id": ObjectId(b["member_id"])}, {"saved_card": 1, "email": 1})
    card = (u or {}).get("saved_card") or {}
    if not card or not card.get("autopay", True):
        return None
    order = {"order_no": "BUD" + uuid.uuid4().hex[:8].upper(), "user_id": b["member_id"],
             "user_email": (u or {}).get("email", ""), "kind": "companion", "ref_id": str(b["_id"]),
             "item_name": b.get("item_name", "Hangout booking"), "quantity": 1,
             "subtotal": amount, "discount": 0.0, "tax": 0.0, "total": amount,
             "tax_percent": 0, "tax_label": "No tax", "credit_applied": 0.0, "charge_credit": 0.0,
             "coupon": "", "currency": b.get("currency", BASE_CURRENCY), "fx_rate": 1,
             "base_currency": BASE_CURRENCY, "charge_subtotal": amount, "charge_discount": 0.0,
             "charge_tax": 0.0, "charge_total": amount,
             "payment_status": "paid", "order_status": "completed", "refund_status": "none",
             "gateway": "saved_card_sim", "transaction_id": "CARD" + uuid.uuid4().hex[:10].upper(),
             "created_at": iso(now_utc()), "paid_at": iso(now_utc())}
    res = await db.orders.insert_one(order)
    await db.payments.insert_one({"order_id": str(res.inserted_id), "user_id": b["member_id"],
                                  "amount": amount, "status": "captured", "gateway": "saved_card_sim",
                                  "transaction_id": order["transaction_id"], "created_at": iso(now_utc())})
    return {"id": str(res.inserted_id), "last4": card["last4"]}


class CounterIn(BaseModel):
    amount: float = Field(gt=0)
    note: str = ""


async def load_booking(bid: str, uid: str, side: str) -> dict:
    try:
        b = await db.companion_bookings.find_one({"_id": ObjectId(bid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid booking id")
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    owner = b["companion_id"] if side == "companion" else b["member_id"]
    if owner != uid:
        raise HTTPException(status_code=403, detail="This isn't your booking.")
    return b


@api.get("/me/bookings")
async def my_bookings(user: dict = Depends(get_current_user)):
    rows = await db.companion_bookings.find(
        {"$or": [{"member_id": user["id"]}, {"companion_id": user["id"]}]}) \
        .sort("created_at", -1).limit(100).to_list(100)
    names = await booking_names(rows)
    return {"items": [booking_view(b, user["id"], names) for b in rows],
            "credit_balance": await credit_balance(user["id"]),
            "free_requests_left": await free_requests_left(user["id"], await membership_active(user["id"])),
            "request_fee": await request_fee()}


class AcceptIn(BaseModel):
    amount: float = 0          # 0 = the companion's listed price for these hours
    note: str = ""


async def try_auto_debit(b: dict, agreed: float) -> Optional[str]:
    """Wallet first, then the saved card — so an accepted hangout confirms without another checkout."""
    if await credit_balance(b["member_id"]) + 0.01 >= agreed:
        await db.credits.insert_one({"user_id": b["member_id"], "amount": -round(agreed, 2), "type": "spent",
                                     "reason": "Hangout paid from your Buddilio wallet",
                                     "booking_id": str(b["_id"]), "created_at": iso(now_utc())})
        await confirm_booking(b, agreed, round(float(b.get("paid_total") or 0) + agreed, 2), "wallet")
        asyncio.create_task(run_auto_reload(b["member_id"]))
        return "wallet"
    charged = await charge_saved_card(b, agreed)
    if charged:
        await confirm_booking(b, agreed, round(float(b.get("paid_total") or 0) + agreed, 2), charged["id"])
        return "card"
    return None


@api.post("/bookings/{bid}/accept")
async def accept_booking(bid: str, payload: AcceptIn = Body(default=AcceptIn()),
                         user: dict = Depends(get_current_user)):
    """The companion says yes and names the price — hourly or for the whole outing."""
    b = await load_booking(bid, user["id"], "companion")
    if b["status"] != "awaiting_acceptance":
        raise HTTPException(status_code=400, detail="This booking isn't waiting on you.")
    listed = round(float(b.get("listed_amount") or b["amount"]), 2)
    agreed = round(float(payload.amount or 0), 2) or listed
    if agreed > listed * 3:
        raise HTTPException(status_code=400, detail="Keep your price within three times your listed rate.")
    await db.companion_bookings.update_one({"_id": b["_id"]}, {"$set": {
        "status": "payment_due", "amount": agreed, "due_amount": agreed,
        "counter_note": payload.note[:300], "accepted_at": iso(now_utc()),
        "item_name": f"{b['hours']}h hangout with {short_name(user.get('full_name', 'a companion'))}"}})
    b = await db.companion_bookings.find_one({"_id": b["_id"]})
    paid_from = await try_auto_debit(b, agreed)
    if paid_from:
        return {"ok": True, "status": "confirmed", "amount": agreed, "paid_from": paid_from}
    await notify(b["member_id"], "Your request was accepted",
                 f"Your companion accepted at {fmt_money(agreed)}. Pay now to lock the hangout in.",
                 "order", "/hangouts/bookings")
    return {"ok": True, "status": "payment_due", "amount": agreed, "due_amount": agreed}


@api.post("/bookings/{bid}/counter")
async def counter_booking(bid: str, payload: CounterIn, user: dict = Depends(get_current_user)):
    """The companion can ask for more than their listed rate; the guest pays the agreed price or walks away."""
    b = await load_booking(bid, user["id"], "companion")
    if b["status"] != "awaiting_acceptance":
        raise HTTPException(status_code=400, detail="This booking isn't waiting on you.")
    amount = round(float(payload.amount), 2)
    listed = round(float(b.get("listed_amount") or b["amount"]), 2)
    if amount <= listed:
        raise HTTPException(status_code=400,
                            detail=f"A counter-offer has to be more than your listed {fmt_money(listed)}.")
    if amount > listed * 3:
        raise HTTPException(status_code=400, detail="Keep counter-offers within three times the listed price.")
    await db.companion_bookings.update_one({"_id": b["_id"]}, {"$set": {
        "status": "counter_offered", "counter_amount": amount, "counter_note": payload.note[:300],
        "due_amount": amount, "countered_at": iso(now_utc()),
        "item_name": f"{b['hours']}h hangout with {short_name(user.get('full_name', 'a companion'))}"}})
    await notify(b["member_id"], "Your companion sent a counter-offer",
                 f"They've asked for {fmt_money(amount)}. Pay it to confirm, or turn the offer down.",
                 "order", "/hangouts/bookings")
    return {"ok": True, "status": "counter_offered", "due_amount": amount}


@api.post("/bookings/{bid}/decline")
async def decline_booking(bid: str, user: dict = Depends(get_current_user)):
    b = await load_booking(bid, user["id"], "companion")
    if b["status"] not in ("awaiting_acceptance", "payment_due", "counter_offered"):
        raise HTTPException(status_code=400, detail="This booking can't be declined now.")
    credit = await grant_credit(b["member_id"], booking_refundable(b),
                               "Your companion couldn't make it, so what you paid is back as Buddilio credit.",
                               str(b["_id"]))
    await db.companion_bookings.update_one({"_id": b["_id"]}, {"$set": {
        "status": "declined", "due_amount": 0, "credit_issued": credit, "closed_at": iso(now_utc())}})
    await notify(b["member_id"], "Hangout request declined",
                 "Your companion turned the request down. The request fee isn't refundable.",
                 "order", "/hangouts/bookings")
    return {"ok": True, "status": "declined", "credit_issued": credit}


@api.post("/bookings/{bid}/reject-counter")
async def reject_counter(bid: str, user: dict = Depends(get_current_user)):
    b = await load_booking(bid, user["id"], "member")
    if b["status"] not in ("payment_due", "counter_offered"):
        raise HTTPException(status_code=400, detail="There's no offer to turn down.")
    credit = await grant_credit(user["id"], booking_refundable(b),
                               "You turned the price down, so your payment is back as Buddilio credit.",
                               str(b["_id"]))
    await db.companion_bookings.update_one({"_id": b["_id"]}, {"$set": {
        "status": "cancelled", "due_amount": 0, "credit_issued": credit, "closed_at": iso(now_utc())}})
    await notify(b["companion_id"], "Counter-offer turned down",
                 "Your guest didn't take the higher price, so the booking is closed.", "order", "/hangouts/host")
    return {"ok": True, "status": "cancelled", "credit_issued": credit}


@api.post("/bookings/{bid}/complete")
async def complete_booking(bid: str, user: dict = Depends(get_current_user)):
    b = await db.companion_bookings.find_one({"_id": ObjectId(bid)})
    if not b or user["id"] not in (b["member_id"], b["companion_id"]):
        raise HTTPException(status_code=404, detail="Booking not found")
    if b["status"] != "confirmed":
        raise HTTPException(status_code=400, detail="Only a confirmed hangout can be marked done.")
    if b["starts_at"] > iso(now_utc()):
        raise HTTPException(status_code=400, detail="You can mark it done once the hangout has started.")
    await db.companion_bookings.update_one({"_id": b["_id"]},
                                          {"$set": {"status": "completed", "completed_at": iso(now_utc())}})
    await db.users.update_one({"_id": ObjectId(b["companion_id"])}, {"$inc": {"companion.completed": 1}})
    return {"ok": True, "status": "completed"}


class RatingIn(BaseModel):
    stars: int = Field(ge=1, le=5)
    note: str = ""


@api.post("/bookings/{bid}/rate")
async def rate_hangout(bid: str, payload: RatingIn, user: dict = Depends(get_current_user)):
    """Private feedback: only the star average and hangout count ever show on a companion's card."""
    b = await load_booking(bid, user["id"], "member")
    if b["status"] != "completed":
        raise HTTPException(status_code=400, detail="You can rate a hangout once it's marked done.")
    if await db.companion_ratings.find_one({"booking_id": bid}):
        raise HTTPException(status_code=400, detail="You've already rated this hangout.")
    await db.companion_ratings.insert_one({
        "booking_id": bid, "member_id": user["id"], "companion_id": b["companion_id"],
        "stars": payload.stars, "note": payload.note[:500], "created_at": iso(now_utc())})
    rows = await db.companion_ratings.find({"companion_id": b["companion_id"]},
                                           {"stars": 1}).limit(500).to_list(500)
    avg = round(sum(r["stars"] for r in rows) / len(rows), 2)
    await db.users.update_one({"_id": ObjectId(b["companion_id"])},
                              {"$set": {"companion.rating": avg, "companion.rating_count": len(rows)}})
    await db.companion_bookings.update_one({"_id": b["_id"]}, {"$set": {"rated": True}})
    return {"ok": True, "rating": avg, "rating_count": len(rows)}


@api.get("/admin/companion-ratings")
async def admin_ratings(companion_id: str = "", user: dict = Depends(require_perm("members:manage"))):
    flt = {"companion_id": companion_id} if companion_id else {}
    rows = await db.companion_ratings.find(flt).sort("created_at", -1).limit(200).to_list(200)
    names = await load_many(db.users, [r["companion_id"] for r in rows] + [r["member_id"] for r in rows],
                            {"full_name": 1})
    return {"items": [{"id": str(r["_id"]), "stars": r["stars"], "note": r.get("note", ""),
                       "created_at": r.get("created_at", ""),
                       "companion_name": short_name((names.get(r["companion_id"]) or {}).get("full_name", "")),
                       "member_name": short_name((names.get(r["member_id"]) or {}).get("full_name", ""))}
                      for r in rows]}


class NoShowIn(BaseModel):
    note: str = ""


@api.post("/bookings/{bid}/no-show")
async def report_no_show(bid: str, payload: NoShowIn, user: dict = Depends(get_current_user)):
    """Money is never refunded, but a no-show turns it into credit and flags the companion for review."""
    b = await load_booking(bid, user["id"], "member")
    if b["status"] != "confirmed":
        raise HTTPException(status_code=400, detail="Only a confirmed hangout can be reported.")
    if b["starts_at"] > iso(now_utc()):
        raise HTTPException(status_code=400, detail="Report this after the start time.")
    credit = await grant_credit(user["id"], booking_refundable(b),
                               "Your companion didn't show, so what you paid is back as Buddilio credit.",
                               str(b["_id"]))
    await db.companion_bookings.update_one({"_id": b["_id"]}, {"$set": {
        "status": "no_show", "credit_issued": credit, "no_show_note": payload.note[:300],
        "closed_at": iso(now_utc())}})
    await db.payouts.update_many({"booking_id": str(b["_id"]), "status": "pending"},
                                 {"$set": {"status": "held", "hold_reason": "Guest reported a no-show"}})
    await db.reports.insert_one({"reporter_id": user["id"], "reporter_email": user["email"],
                                 "target_type": "user", "target_id": b["companion_id"],
                                 "reason": "Hangout no-show", "details": payload.note[:300],
                                 "status": "open", "created_at": iso(now_utc())})
    return {"ok": True, "status": "no_show", "credit_issued": credit}


# ---- admin side ----
class CompanionModIn(BaseModel):
    action: str
    reason: str = ""


@api.get("/admin/companions")
async def admin_companions(status: str = "pending", user: dict = Depends(require_perm("members:manage"))):
    flt: dict[str, Any] = {"companion": {"$exists": True}}
    if status != "all":
        flt["companion.status"] = status
    docs = await db.users.find(flt).sort("companion.applied_at", -1).limit(200).to_list(200)
    counts = {s: await db.users.count_documents({"companion.status": s})
              for s in ("pending", "approved", "rejected", "suspended")}
    return {"items": [companion_card(d) | {"email": d.get("email", ""), "full_name": d.get("full_name", ""),
                                           "applied_at": (d.get("companion") or {}).get("applied_at", "")}
                      for d in docs],
            "counts": counts, "cut_percent": COMPANION_CUT}


@api.post("/admin/companions/{cid}")
async def moderate_companion(cid: str, payload: CompanionModIn,
                             user: dict = Depends(require_perm("members:manage"))):
    if payload.action not in ("approve", "reject", "suspend"):
        raise HTTPException(status_code=400, detail="Unknown action")
    try:
        doc = await db.users.find_one({"_id": ObjectId(cid), "companion": {"$exists": True}})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid member id")
    if not doc:
        raise HTTPException(status_code=404, detail="No hangout profile for that member.")
    state = {"approve": "approved", "reject": "rejected", "suspend": "suspended"}[payload.action]
    await db.users.update_one({"_id": doc["_id"]}, {"$set": {
        "companion.status": state, "companion.rejected_reason": payload.reason[:300] if state != "approved" else "",
        "companion.enabled": state == "approved",
        "companion.reviewed_at": iso(now_utc())}})
    await audit(user, f"companion.{payload.action}", "user", cid, {"reason": payload.reason[:120]})
    msg = {"approved": "You're live — premium members can now book time with you.",
           "rejected": payload.reason or "We can't list your hangout profile right now.",
           "suspended": payload.reason or "Your hangout profile has been paused by our team."}[state]
    await notify(cid, f"Hangout profile {state}", msg, "system", "/hangouts/host")
    return {"ok": True, "status": state}


@api.get("/admin/companion-bookings")
async def admin_bookings(status: str = "", user: dict = Depends(require_perm("finance:view",
                                                                            "members:manage"))):
    flt = {"status": status} if status else {}
    rows = await db.companion_bookings.find(flt).sort("created_at", -1).limit(200).to_list(200)
    names = await booking_names(rows)
    gross = round(sum(float(r.get("paid_total") or 0) for r in rows), 2)
    return {"items": [booking_view(b, "", names) | {"member_name": names.get(b["member_id"], ""),
                                                    "companion_name": names.get(b["companion_id"], "")}
                      for b in rows],
            "totals": {"bookings": len(rows), "gross": gross,
                       "platform": round(sum(float(r.get("platform_fee") or 0) for r in rows), 2),
                       "companions": round(sum(float(r.get("companion_net") or 0) for r in rows), 2)},
            "cut_percent": COMPANION_CUT}


class CreditIn(BaseModel):
    amount: float = Field(gt=0)
    reason: str = ""


@api.post("/admin/companion-bookings/{bid}/credit")
async def admin_grant_credit(bid: str, payload: CreditIn,
                             user: dict = Depends(require_perm("finance:manage"))):
    """Payments are non-refundable — this is the goodwill lever when a guest deserves something back."""
    try:
        b = await db.companion_bookings.find_one({"_id": ObjectId(bid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid booking id")
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    if payload.amount > float(b["amount"]):
        raise HTTPException(status_code=400, detail="Credit can't be more than the booking price.")
    credit = await grant_credit(b["member_id"], payload.amount,
                               payload.reason or "Buddilio credit added by our team.", bid)
    await audit(user, "companion.credit", "booking", bid, {"amount": credit, "reason": payload.reason[:120]})
    return {"ok": True, "credit_issued": credit}


# ---------------- solo travel: trips, providers, service requests ----------------
# Trips are free for every member. Providers pay once to be listed, then Buddilio takes a cut of each
# booking. Prices shown to travellers carry a markup on the provider's own rate, and everywhere outside
# India pays the international uplift.
PROVIDER_FEE_DEFAULT = float(os.environ.get("PROVIDER_FEE", "999"))
TRAVEL_MARKUP_DEFAULT = 18.0            # 15–20% band the founder asked for
TRAVEL_UPLIFT_DEFAULT = 30.0            # non-India uplift on every booking
TRAVEL_CUT_DEFAULT = 25.0


async def travel_config() -> dict:
    s = await db.settings.find_one({}, {"provider_fee": 1, "travel_markup_percent": 1,
                                        "travel_uplift_percent": 1, "travel_cut_percent": 1}) or {}

    def num(key, default):
        try:
            return round(float(s.get(key)), 2)
        except (TypeError, ValueError):
            return default

    return {"fee": num("provider_fee", PROVIDER_FEE_DEFAULT),
            "markup_percent": num("travel_markup_percent", TRAVEL_MARKUP_DEFAULT),
            "uplift_percent": num("travel_uplift_percent", TRAVEL_UPLIFT_DEFAULT),
            "cut_percent": num("travel_cut_percent", TRAVEL_CUT_DEFAULT)}


def uplift_factor(country_code: str, cfg: dict) -> float:
    """India pays the base rate; everywhere else carries the international uplift."""
    return 1.0 if (country_code or "").upper() == "IN" else 1 + cfg["uplift_percent"] / 100


def listed_price(day_rate: float, cfg: dict, country_code: str) -> float:
    return round(day_rate * (1 + cfg["markup_percent"] / 100) * uplift_factor(country_code, cfg), 2)


class ProviderIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    roles: List[str]
    day_rate: float = Field(gt=0)
    destinations: List[str] = []
    languages: List[str] = []
    headline: str = ""
    about: str = ""
    experience_years: int = Field(default=0, ge=0, le=60)
    documents: List[dict] = []
    accept_terms: bool = False


def provider_card(u: dict, cfg: dict, country_code: str, mine: bool = False) -> dict:
    p = u.get("provider") or {}
    out = {"id": str(u["_id"]), "name": short_name(u.get("full_name", "Member")),
           "photo": u.get("photo", ""), "roles": p.get("roles", []),
           "destinations": p.get("destinations", []), "languages": p.get("languages", []),
           "headline": p.get("headline", ""), "about": p.get("about", ""),
           "experience_years": p.get("experience_years", 0), "trips_done": p.get("trips_done", 0),
           "rating": p.get("rating", 0), "rating_count": p.get("rating_count", 0),
           "verified": bool(u.get("verified")), "status": p.get("status", "none"),
           "day_price": listed_price(float(p.get("day_rate") or 0), cfg, country_code),
           "currency": BASE_CURRENCY}
    if mine:
        out |= {"day_rate": p.get("day_rate", 0), "fee_paid": p.get("fee_paid", 0),
                "documents": p.get("documents", []), "rejected_reason": p.get("rejected_reason", ""),
                "cut_percent": cfg["cut_percent"], "markup_percent": cfg["markup_percent"],
                "terms": TRAVEL_TERMS}
    return out


@api.get("/travel/meta")
async def travel_meta(user: dict = Depends(get_current_user)):
    cfg = await travel_config()
    fee = round(cfg["fee"] * uplift_factor(user.get("country_code", ""), cfg), 2)
    return {"roles": PROVIDER_ROLES, "activities": TRIP_ACTIVITIES, "terms": TRAVEL_TERMS,
            "provider_fee": fee, "markup_percent": cfg["markup_percent"],
            "uplift_percent": cfg["uplift_percent"], "currency": BASE_CURRENCY}


# ---- provider onboarding ----
@api.get("/me/provider")
async def my_provider(user: dict = Depends(get_current_user)):
    cfg = await travel_config()
    doc = await db.users.find_one({"_id": ObjectId(user["id"])})
    fee = round(cfg["fee"] * uplift_factor(doc.get("country_code", ""), cfg), 2)
    return {"profile": provider_card(doc, cfg, doc.get("country_code", ""), mine=True),
            "provider_fee": fee, "roles": PROVIDER_ROLES, "terms": TRAVEL_TERMS}


@api.post("/me/provider")
async def apply_as_provider(payload: ProviderIn, user: dict = Depends(get_current_user)):
    """Anyone can offer their services; they pay the one-time fee, then an admin checks the documents."""
    doc = await db.users.find_one({"_id": ObjectId(user["id"])})
    roles = [r for r in payload.roles if r in {x["key"] for x in PROVIDER_ROLES}][:9]
    if not roles:
        raise HTTPException(status_code=400, detail="Pick at least one service you offer.")
    if not payload.accept_terms:
        raise HTTPException(status_code=400, detail="Please accept the travel terms to continue.")
    files = []
    for d in (payload.documents or [])[:5]:
        url = str(d.get("url", ""))
        if not url.startswith("/api/files/"):
            raise HTTPException(status_code=400, detail="Upload your documents through Buddilio first.")
        files.append({"url": url, "name": str(d.get("name", "Document"))[:120]})
    if not files:
        raise HTTPException(status_code=400, detail="Attach at least one ID or licence.")
    cfg = await travel_config()
    existing = doc.get("provider") or {}
    fee = round(cfg["fee"] * uplift_factor(doc.get("country_code", ""), cfg), 2)
    paid = float(existing.get("fee_paid") or 0) > 0
    p = {"roles": roles, "day_rate": round(payload.day_rate, 2),
         "destinations": [d[:60] for d in payload.destinations][:12],
         "languages": [l[:30] for l in payload.languages][:6],
         "headline": payload.headline[:120], "about": safe_html(payload.about)[:4000],
         "experience_years": payload.experience_years, "documents": files,
         "status": existing.get("status") if existing.get("status") == "approved"
                   else ("pending" if paid else "pending_fee"),
         "fee_paid": existing.get("fee_paid", 0), "fee": fee,
         "trips_done": existing.get("trips_done", 0), "rating": existing.get("rating", 0),
         "rating_count": existing.get("rating_count", 0), "rejected_reason": "",
         "accepted_terms_at": iso(now_utc()),
         "applied_at": existing.get("applied_at") or iso(now_utc())}
    await db.users.update_one({"_id": doc["_id"]}, {"$set": {"provider": p}})
    if not paid:
        return {"ok": True, "status": "pending_fee", "provider_fee": fee, "next": "checkout",
                "checkout": {"kind": "provider_fee", "item_id": user["id"], "amount": fee}}
    return {"ok": True, "status": p["status"], "next": "review"}


async def fulfil_provider_fee(order: dict, uid: str):
    doc = await db.users.find_one({"_id": ObjectId(uid)}, {"provider": 1, "full_name": 1})
    p = (doc or {}).get("provider") or {}
    if not p or float(p.get("fee_paid") or 0) > 0:
        return
    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": {
        "provider.fee_paid": float(order["total"]), "provider.fee_order_id": str(order["_id"]),
        "provider.status": "approved" if p.get("status") == "approved" else "pending",
        "provider.paid_at": iso(now_utc())}})
    await notify(uid, "Registration fee received",
                 "Thanks — our team reviews new travel providers within a business day.",
                 "system", "/travel/provider")


@api.get("/admin/providers")
async def admin_providers(status: str = "pending", user: dict = Depends(require_perm("verification:manage"))):
    cfg = await travel_config()
    flt: dict[str, Any] = {"provider": {"$exists": True}}
    if status and status != "all":
        flt["provider.status"] = status
    docs = await db.users.find(flt).sort("provider.applied_at", -1).limit(200).to_list(200)
    counts = {s: await db.users.count_documents({"provider.status": s})
              for s in ("pending_fee", "pending", "approved", "rejected")}
    items = []
    for d in docs:
        card = provider_card(d, cfg, d.get("country_code", ""), mine=True)
        card |= {"email": mask_email(d.get("email", "")), "city": d.get("city", ""),
                 "country": d.get("country", ""), "full_name": d.get("full_name", "")}
        items.append(card)
    return {"items": items, "counts": counts, "roles": PROVIDER_ROLES, "config": cfg}


@api.post("/admin/providers/{uid}")
async def moderate_provider(uid: str, payload: VerifyIn,
                            user: dict = Depends(require_perm("verification:manage"))):
    if payload.action not in ("approve", "reject", "suspend"):
        raise HTTPException(status_code=400, detail="Unknown action")
    try:
        doc = await db.users.find_one({"_id": ObjectId(uid), "provider": {"$exists": True}})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid member id")
    if not doc:
        raise HTTPException(status_code=404, detail="No provider application from that member.")
    if payload.action == "approve" and float((doc.get("provider") or {}).get("fee_paid") or 0) <= 0:
        raise HTTPException(status_code=400, detail="They haven't paid the registration fee yet.")
    state = {"approve": "approved", "reject": "rejected", "suspend": "suspended"}[payload.action]
    await db.users.update_one({"_id": doc["_id"]}, {"$set": {
        "provider.status": state, "provider.rejected_reason": payload.note[:300],
        "provider.reviewed_at": iso(now_utc())}})
    await audit(user, f"provider.{payload.action}", "user", uid, {"note": payload.note[:120]})
    await notify(uid, f"Travel provider profile {state}",
                 "You're listed — travellers can book you now." if state == "approved"
                 else (payload.note or "Our team couldn't approve your profile yet."),
                 "moderation", "/travel/provider")
    return {"ok": True, "status": state}


@api.get("/travel/providers")
async def list_providers(role: str = "", destination: str = "", q: str = "",
                         sort: Literal["price", "price_desc", "rating", "experience"] = "rating",
                         page: int = 1, limit: int = 12, user: dict = Depends(get_current_user)):
    cfg = await travel_config()
    flt: dict[str, Any] = {"provider.status": "approved", "status": "active"}
    if role:
        flt["provider.roles"] = role
    if destination:
        flt["provider.destinations"] = {"$regex": destination, "$options": "i"}
    if q:
        flt["$or"] = [{"full_name": {"$regex": q, "$options": "i"}},
                      {"provider.headline": {"$regex": q, "$options": "i"}}]
    order = {"rating": [("provider.rating", -1), ("provider.trips_done", -1)],
             "experience": [("provider.experience_years", -1), ("provider.trips_done", -1)],
             "price_desc": [("provider.day_rate", -1)]}.get(sort, [("provider.day_rate", 1)])
    total = await db.users.count_documents(flt)
    docs = await db.users.find(flt).sort(order).skip((page - 1) * limit).limit(limit).to_list(limit)
    cc = user.get("country_code", "")
    return {"items": [provider_card(d, cfg, cc) for d in docs], "total": total, "page": page,
            "roles": PROVIDER_ROLES, "currency": BASE_CURRENCY, "terms": TRAVEL_TERMS}


@api.get("/travel/providers/{pid}")
async def provider_detail(pid: str, user: dict = Depends(get_current_user)):
    cfg = await travel_config()
    try:
        doc = await db.users.find_one({"_id": ObjectId(pid), "provider.status": "approved"})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid provider id")
    if not doc:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider_card(doc, cfg, user.get("country_code", "")) | {"terms": TRAVEL_TERMS}


# ---- trips: free to post, free to join ----
class TripIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    destination: str
    country: str = ""
    starts_at: str
    ends_at: str = ""
    activity: str = "Trekking"
    group_size: int = Field(default=4, ge=2, le=30)
    budget: float = 0
    gender_pref: Literal["any", "women", "men"] = "any"
    notes: str = ""


def trip_view(t: dict, me: str, names: dict) -> dict:
    host = names.get(t["host_id"]) or {}
    return {"id": str(t["_id"]), "title": t["title"], "destination": t["destination"],
            "country": t.get("country", ""), "starts_at": t["starts_at"], "ends_at": t.get("ends_at", ""),
            "activity": t["activity"], "group_size": t["group_size"], "budget": t.get("budget", 0),
            "gender_pref": t.get("gender_pref", "any"), "notes": t.get("notes", ""),
            "status": t.get("status", "open"), "joined": t.get("joined", 0),
            "host_id": t["host_id"], "host_name": short_name(host.get("full_name", "Member")),
            "host_photo": host.get("photo", ""), "host_verified": bool(host.get("verified")),
            "is_host": t["host_id"] == me, "currency": BASE_CURRENCY,
            "created_at": t.get("created_at", "")}


@api.post("/travel/trips")
async def create_trip(payload: TripIn, user: dict = Depends(get_current_user)):
    try:
        starts = datetime.fromisoformat(payload.starts_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Pick a valid start date.")
    if starts < now_utc():
        raise HTTPException(status_code=400, detail="Trips have to start in the future.")
    if payload.activity not in TRIP_ACTIVITIES:
        raise HTTPException(status_code=400, detail="Choose one of the listed activities.")
    live = await db.trips.count_documents({"host_id": user["id"], "status": "open"})
    if live >= 5:
        raise HTTPException(status_code=400, detail="You already have five open trips — close one first.")
    doc = payload.model_dump() | {
        "host_id": user["id"], "status": "open", "joined": 0,
        "destination": payload.destination.strip()[:80], "title": payload.title.strip()[:120],
        "notes": safe_html(payload.notes)[:4000], "starts_at": iso(starts),
        "country": payload.country or (country_for_city(payload.destination) or {}).get("name", ""),
        "created_at": iso(now_utc())}
    res = await db.trips.insert_one(doc)
    t = await db.trips.find_one({"_id": res.inserted_id})
    names = await load_many(db.users, [user["id"]], {"full_name": 1, "photo": 1, "verified": 1})
    return trip_view(t, user["id"], names)


@api.get("/travel/trips")
async def list_trips(destination: str = "", activity: str = "", mine: bool = False,
                     page: int = 1, limit: int = 12, user: dict = Depends(get_current_user)):
    flt: dict[str, Any] = {"status": "open"} if not mine else {"host_id": user["id"]}
    if destination:
        flt["destination"] = {"$regex": destination, "$options": "i"}
    if activity:
        flt["activity"] = activity
    total = await db.trips.count_documents(flt)
    rows = await db.trips.find(flt).sort("starts_at", 1).skip((page - 1) * limit).limit(limit).to_list(limit)
    names = await load_many(db.users, [t["host_id"] for t in rows],
                            {"full_name": 1, "photo": 1, "verified": 1})
    joined = {j["trip_id"] for j in await db.trip_joins.find(
        {"user_id": user["id"], "trip_id": {"$in": [str(t["_id"]) for t in rows]}},
        {"trip_id": 1}).to_list(200)}
    items = []
    for t in rows:
        v = trip_view(t, user["id"], names)
        v["requested"] = v["id"] in joined
        items.append(v)
    return {"items": items, "total": total, "page": page, "activities": TRIP_ACTIVITIES,
            "terms": TRAVEL_TERMS}


@api.post("/travel/trips/{tid}/join")
async def join_trip(tid: str, body: dict = Body(default={}), user: dict = Depends(get_current_user)):
    """Joining is free — the host just has to say yes."""
    try:
        t = await db.trips.find_one({"_id": ObjectId(tid), "status": "open"})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid trip id")
    if not t:
        raise HTTPException(status_code=404, detail="That trip isn't open any more.")
    if t["host_id"] == user["id"]:
        raise HTTPException(status_code=400, detail="It's your own trip.")
    if await db.trip_joins.find_one({"trip_id": tid, "user_id": user["id"]}):
        raise HTTPException(status_code=400, detail="You've already asked to join this trip.")
    if t.get("joined", 0) >= t["group_size"] - 1:
        raise HTTPException(status_code=400, detail="This group is full.")
    await db.trip_joins.insert_one({"trip_id": tid, "user_id": user["id"], "status": "requested",
                                    "note": str(body.get("note", ""))[:500], "created_at": iso(now_utc())})
    await notify(t["host_id"], "Someone wants to join your trip",
                 f"{short_name(user['full_name'])} asked to join {t['title']}.",
                 "connection", "/travel/trips")
    return {"ok": True, "status": "requested"}


@api.get("/travel/trips/{tid}/requests")
async def trip_requests(tid: str, user: dict = Depends(get_current_user)):
    try:
        t = await db.trips.find_one({"_id": ObjectId(tid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid trip id")
    if not t or t["host_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the host can see who asked to join.")
    rows = await db.trip_joins.find({"trip_id": tid}).sort("created_at", 1).limit(100).to_list(100)
    people = await load_many(db.users, [r["user_id"] for r in rows],
                             {"full_name": 1, "photo": 1, "city": 1, "verified": 1, "age": 1})
    return {"items": [{"id": str(r["_id"]), "user_id": r["user_id"], "status": r["status"],
                       "note": r.get("note", ""), "created_at": r.get("created_at", ""),
                       "name": short_name((people.get(r["user_id"]) or {}).get("full_name", "")),
                       "photo": (people.get(r["user_id"]) or {}).get("photo", ""),
                       "city": (people.get(r["user_id"]) or {}).get("city", ""),
                       "verified": bool((people.get(r["user_id"]) or {}).get("verified"))}
                      for r in rows]}


@api.post("/travel/trips/{tid}/requests/{jid}")
async def decide_trip_request(tid: str, jid: str, payload: VerifyIn,
                              user: dict = Depends(get_current_user)):
    if payload.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Unknown action")
    try:
        t = await db.trips.find_one({"_id": ObjectId(tid)})
        j = await db.trip_joins.find_one({"_id": ObjectId(jid), "trip_id": tid})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    if not t or not j:
        raise HTTPException(status_code=404, detail="Request not found")
    if t["host_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the host decides who joins.")
    if j["status"] != "requested":
        raise HTTPException(status_code=400, detail="You've already answered this one.")
    state = "joined" if payload.action == "approve" else "declined"
    await db.trip_joins.update_one({"_id": j["_id"]}, {"$set": {"status": state,
                                                               "decided_at": iso(now_utc())}})
    if state == "joined":
        await db.trips.update_one({"_id": t["_id"]}, {"$inc": {"joined": 1}})
        full = t.get("joined", 0) + 1 >= t["group_size"] - 1
        if full:
            await db.trips.update_one({"_id": t["_id"]}, {"$set": {"status": "full"}})
    await notify(j["user_id"], f"Trip request {state}",
                 f"{t['title']} · {t['destination']}" if state == "joined"
                 else f"The host couldn't fit you into {t['title']} this time.",
                 "connection", "/travel/trips")
    return {"ok": True, "status": state}


@api.delete("/travel/trips/{tid}")
async def close_trip(tid: str, user: dict = Depends(get_current_user)):
    try:
        t = await db.trips.find_one({"_id": ObjectId(tid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid trip id")
    if not t:
        raise HTTPException(status_code=404, detail="Trip not found")
    if t["host_id"] != user["id"] and "members:manage" not in perms_of(user):
        raise HTTPException(status_code=403, detail="Only the host can close this trip.")
    await db.trips.update_one({"_id": t["_id"]}, {"$set": {"status": "closed"}})
    return {"ok": True, "status": "closed"}


# ---- service requests and provider bookings ----
class ServiceRequestIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    destination: str
    roles: List[str]
    starts_at: str
    days: int = Field(default=1, ge=1, le=30)
    people: int = Field(default=1, ge=1, le=30)
    budget: float = 0
    notes: str = ""


class QuoteIn(BaseModel):
    amount: float = Field(gt=0)
    note: str = ""


@api.post("/travel/requests")
async def create_service_request(payload: ServiceRequestIn, user: dict = Depends(get_current_user)):
    roles = [r for r in payload.roles if r in {x["key"] for x in PROVIDER_ROLES}][:4]
    if not roles:
        raise HTTPException(status_code=400, detail="Pick at least one service you need.")
    try:
        starts = datetime.fromisoformat(payload.starts_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Pick a valid start date.")
    if starts < now_utc():
        raise HTTPException(status_code=400, detail="Requests have to start in the future.")
    doc = payload.model_dump() | {"roles": roles, "traveller_id": user["id"], "status": "open",
                                  "destination": payload.destination.strip()[:80],
                                  "notes": safe_html(payload.notes)[:2000],
                                  "starts_at": iso(starts), "created_at": iso(now_utc())}
    res = await db.service_requests.insert_one(doc)
    return clean(await db.service_requests.find_one({"_id": res.inserted_id}))


@api.get("/travel/requests")
async def list_service_requests(mine: bool = False, user: dict = Depends(get_current_user)):
    """Travellers see their own; approved providers see open requests matching their roles."""
    if mine:
        flt: dict[str, Any] = {"traveller_id": user["id"]}
    else:
        doc = await db.users.find_one({"_id": ObjectId(user["id"])}, {"provider": 1})
        p = (doc or {}).get("provider") or {}
        if p.get("status") != "approved":
            raise HTTPException(status_code=403, detail="Only listed providers can browse open requests.")
        flt = {"status": "open", "roles": {"$in": p.get("roles", [])}}
    rows = await db.service_requests.find(flt).sort("created_at", -1).limit(60).to_list(60)
    ids = [str(r["_id"]) for r in rows]
    quotes = await db.service_quotes.find({"request_id": {"$in": ids}}).limit(500).to_list(500)
    names = await load_many(db.users, [r["traveller_id"] for r in rows], {"full_name": 1, "photo": 1})
    items = []
    for r in rows:
        rid = str(r["_id"])
        mine_quotes = [q for q in quotes if q["request_id"] == rid]
        items.append(clean(r) | {
            "traveller_name": short_name((names.get(r["traveller_id"]) or {}).get("full_name", "")),
            "quote_count": len(mine_quotes),
            "my_quote": next((round(q["amount"], 2) for q in mine_quotes
                              if q["provider_id"] == user["id"]), 0),
            "quotes": [{"id": str(q["_id"]), "provider_id": q["provider_id"], "amount": q["amount"],
                        "note": q.get("note", ""), "status": q.get("status", "open"),
                        "provider_name": q.get("provider_name", "")}
                       for q in mine_quotes] if r["traveller_id"] == user["id"] else []})
    return {"items": items, "roles": PROVIDER_ROLES}


@api.post("/travel/requests/{rid}/quotes")
async def send_quote(rid: str, payload: QuoteIn, user: dict = Depends(get_current_user)):
    doc = await db.users.find_one({"_id": ObjectId(user["id"])}, {"provider": 1, "full_name": 1})
    if ((doc or {}).get("provider") or {}).get("status") != "approved":
        raise HTTPException(status_code=403, detail="Only listed providers can quote.")
    try:
        req = await db.service_requests.find_one({"_id": ObjectId(rid), "status": "open"})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request id")
    if not req:
        raise HTTPException(status_code=404, detail="That request is closed.")
    if await db.service_quotes.find_one({"request_id": rid, "provider_id": user["id"]}):
        raise HTTPException(status_code=400, detail="You've already quoted on this request.")
    cfg = await travel_config()
    traveller = await db.users.find_one({"_id": ObjectId(req["traveller_id"])}, {"country_code": 1})
    price = listed_price(round(payload.amount, 2), cfg, (traveller or {}).get("country_code", ""))
    res = await db.service_quotes.insert_one({
        "request_id": rid, "provider_id": user["id"], "provider_name": short_name(doc.get("full_name", "")),
        "provider_amount": round(payload.amount, 2), "amount": price,
        "note": payload.note[:500], "status": "open", "created_at": iso(now_utc())})
    await notify(req["traveller_id"], "New quote for your trip",
                 f"{short_name(doc.get('full_name', 'A provider'))} quoted {fmt_money(price)} "
                 f"for {req['destination']}.", "order", "/travel/requests")
    return {"ok": True, "quote_id": str(res.inserted_id), "amount": price}


class ProviderBookingIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    days: int = Field(default=1, ge=1, le=30)
    starts_at: str
    people: int = Field(default=1, ge=1, le=30)
    notes: str = ""


async def open_travel_booking(traveller: dict, provider_id: str, amount: float, days: int,
                              starts: str, label: str, request_id: str = "") -> dict:
    cfg = await travel_config()
    cut = round(amount * cfg["cut_percent"] / 100, 2)
    doc = {"traveller_id": traveller["id"], "provider_id": provider_id, "days": days,
           "amount": round(amount, 2), "due_amount": round(amount, 2), "paid_total": 0.0,
           "cut_percent": cfg["cut_percent"], "platform_fee": cut, "provider_net": round(amount - cut, 2),
           "currency": BASE_CURRENCY, "status": "pending_payment", "starts_at": starts,
           "request_id": request_id, "item_name": label[:120], "created_at": iso(now_utc())}
    res = await db.travel_bookings.insert_one(doc)
    return {"booking_id": str(res.inserted_id), "amount": doc["amount"],
            "checkout": {"kind": "travel", "item_id": str(res.inserted_id), "amount": doc["amount"]}}


@api.post("/travel/providers/{pid}/bookings")
async def book_provider(pid: str, payload: ProviderBookingIn, user: dict = Depends(get_current_user)):
    cfg = await travel_config()
    try:
        doc = await db.users.find_one({"_id": ObjectId(pid), "provider.status": "approved"})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid provider id")
    if not doc:
        raise HTTPException(status_code=404, detail="Provider not available")
    if pid == user["id"]:
        raise HTTPException(status_code=400, detail="You can't book yourself.")
    try:
        starts = datetime.fromisoformat(payload.starts_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Pick a valid start date.")
    if starts < now_utc():
        raise HTTPException(status_code=400, detail="Pick a date in the future.")
    day_price = listed_price(float((doc.get("provider") or {}).get("day_rate") or 0), cfg,
                             user.get("country_code", ""))
    amount = round(day_price * payload.days, 2)
    return await open_travel_booking(user, pid, amount, payload.days, iso(starts),
                                     f"{payload.days}-day service · {short_name(doc.get('full_name', ''))}")


@api.post("/travel/quotes/{qid}/accept")
async def accept_quote(qid: str, user: dict = Depends(get_current_user)):
    try:
        q = await db.service_quotes.find_one({"_id": ObjectId(qid), "status": "open"})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid quote id")
    if not q:
        raise HTTPException(status_code=404, detail="That quote is no longer open.")
    req = await db.service_requests.find_one({"_id": ObjectId(q["request_id"])})
    if not req or req["traveller_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the traveller can accept a quote.")
    out = await open_travel_booking(user, q["provider_id"], float(q["amount"]), int(req.get("days", 1)),
                                    req["starts_at"], f"{req['destination']} · {q['provider_name']}",
                                    q["request_id"])
    await db.service_quotes.update_one({"_id": q["_id"]}, {"$set": {"status": "accepted",
                                                                   "booking_id": out["booking_id"]}})
    await db.service_requests.update_one({"_id": req["_id"]}, {"$set": {"status": "matched"}})
    return out


async def fulfil_travel(order: dict, uid: str):
    b = await db.travel_bookings.find_one({"_id": ObjectId(order["ref_id"])})
    if not b or b["traveller_id"] != uid or b["status"] != "pending_payment":
        return
    await db.travel_bookings.update_one({"_id": b["_id"]}, {"$set": {
        "status": "confirmed", "paid_total": round(float(order["total"]), 2), "due_amount": 0,
        "order_id": str(order["_id"]), "confirmed_at": iso(now_utc())}})
    await db.payouts.insert_one({
        "partner_id": b["provider_id"], "booking_id": str(b["_id"]), "kind": "travel",
        "event_id": "", "event_title": f"Travel service · {b['days']}d from {b['starts_at'][:10]}",
        "orders": 1, "gross": b["amount"], "fee_percent": b["cut_percent"], "fee": b["platform_fee"],
        "net": b["provider_net"], "currency": b.get("currency", BASE_CURRENCY),
        "status": "pending", "created_at": iso(now_utc())})
    await db.users.update_one({"_id": ObjectId(b["provider_id"])}, {"$inc": {"provider.trips_done": 1}})
    await notify(b["provider_id"], "You've been booked",
                 f"A traveller paid for {b['days']} day(s) from {b['starts_at'][:10]}. "
                 f"Your payout is {fmt_money(b['provider_net'])}.", "order", "/travel/provider")
    await notify(uid, "Travel service confirmed",
                 "Your provider has been notified and paid through Buddilio.", "order", "/travel/bookings")


@api.get("/travel/bookings")
async def my_travel_bookings(user: dict = Depends(get_current_user)):
    rows = await db.travel_bookings.find({"$or": [{"traveller_id": user["id"]},
                                                  {"provider_id": user["id"]}]}) \
        .sort("created_at", -1).limit(60).to_list(60)
    names = await load_many(db.users, [r["traveller_id"] for r in rows] + [r["provider_id"] for r in rows],
                            {"full_name": 1, "photo": 1})
    items = []
    for b in rows:
        mine_role = "traveller" if b["traveller_id"] == user["id"] else "provider"
        other = b["provider_id"] if mine_role == "traveller" else b["traveller_id"]
        items.append({"id": str(b["_id"]), "role": mine_role, "status": b["status"],
                      "days": b["days"], "amount": b["amount"], "due_amount": b.get("due_amount", 0),
                      "starts_at": b["starts_at"], "item_name": b.get("item_name", ""),
                      "provider_net": b["provider_net"] if mine_role == "provider" else 0,
                      "with_name": short_name((names.get(other) or {}).get("full_name", "Member")),
                      "created_at": b.get("created_at", "")})
    return {"items": items}


# ---------------- finance: ledger, invoices, receipts, exports ----------------
# Every rupee in (orders) and out (payouts) lands in one filterable ledger, with a printable invoice for
# money we collect and a receipt/voucher for money we pass on.
MONEY_IN_KINDS = {"membership": "Membership", "product": "Store", "event": "Event ticket",
                  "companion": "Hangout", "wallet": "Wallet top-up", "travel": "Travel service",
                  "provider_fee": "Provider registration"}


def invoice_no(order: dict) -> str:
    return "INV-" + (order.get("order_no") or str(order["_id"])[-8:].upper())


def receipt_no(order: dict) -> str:
    return "RCP-" + (order.get("order_no") or str(order["_id"])[-8:].upper())


async def commission_for(order: dict) -> float:
    """What Buddilio keeps on this order: the whole thing, unless a payout hands most of it on."""
    if order["kind"] in ("companion", "travel"):
        p = await db.payouts.find_one({"booking_id": order.get("ref_id", "")}, {"fee": 1})
        if p:
            return round(float(p.get("fee") or 0), 2)
    if order["kind"] == "event":
        return 0.0                      # organiser payouts settle event revenue separately
    if order["kind"] == "wallet":
        return 0.0                      # credit we still owe the member
    return round(float(order.get("total") or 0), 2)


def ledger_line(order: dict, commission: float, name: str) -> dict:
    return {"id": str(order["_id"]), "date": order.get("paid_at") or order.get("created_at", ""),
            "direction": "in", "reference": invoice_no(order), "order_no": order.get("order_no", ""),
            "kind": order["kind"], "kind_label": MONEY_IN_KINDS.get(order["kind"], order["kind"]),
            "client": name, "client_id": order.get("user_id", ""), "email": order.get("user_email", ""),
            "description": order.get("item_name", ""), "gross": round(float(order.get("total") or 0), 2),
            "tax": round(float(order.get("tax") or 0), 2), "commission": commission,
            "payout": round(round(float(order.get("total") or 0), 2) - commission, 2),
            "status": order.get("refund_status") if order.get("refund_status", "none") != "none"
                      else order.get("payment_status", ""),
            "gateway": order.get("gateway", ""), "currency": order.get("currency", BASE_CURRENCY)}


def payout_line(p: dict, name: str) -> dict:
    return {"id": str(p["_id"]), "date": p.get("paid_at") or p.get("created_at", ""),
            "direction": "out", "reference": "PO-" + str(p["_id"])[-8:].upper(),
            "order_no": "", "kind": p.get("kind", "event"), "kind_label": "Payout",
            "client": name, "client_id": p.get("partner_id", ""), "email": "",
            "description": p.get("event_title", ""), "gross": round(float(p.get("gross") or 0), 2),
            "tax": 0.0, "commission": round(float(p.get("fee") or 0), 2),
            "payout": round(float(p.get("net") or 0), 2), "status": p.get("status", "pending"),
            "gateway": "", "currency": p.get("currency", BASE_CURRENCY)}


async def ledger_rows(frm: str, to: str, kind: str, direction: str, q: str, status: str) -> list:
    span: dict[str, Any] = {}
    if frm:
        span["$gte"] = frm
    if to:
        span["$lte"] = to + "T23:59:59"
    rows = []
    if direction in ("", "all", "in"):
        flt: dict[str, Any] = {"payment_status": "paid"}
        if span:
            flt["created_at"] = span
        if kind and kind in MONEY_IN_KINDS:
            flt["kind"] = kind
        if status and status != "all":
            flt["$or"] = [{"payment_status": status}, {"refund_status": status}]
        if q:
            flt["$and"] = [{"$or": [{"user_email": {"$regex": q, "$options": "i"}},
                                    {"item_name": {"$regex": q, "$options": "i"}},
                                    {"order_no": {"$regex": q, "$options": "i"}}]}]
        orders = await db.orders.find(flt).sort("created_at", -1).limit(1000).to_list(1000)
        names = await load_many(db.users, [o.get("user_id", "") for o in orders], {"full_name": 1})
        for o in orders:
            rows.append(ledger_line(o, await commission_for(o),
                                    (names.get(o.get("user_id", "")) or {}).get("full_name", "Guest")))
    if direction in ("", "all", "out"):
        pflt: dict[str, Any] = {}
        if span:
            pflt["created_at"] = span
        if status and status != "all":
            pflt["status"] = status
        payouts = await db.payouts.find(pflt).sort("created_at", -1).limit(1000).to_list(1000)
        pnames = await load_many(db.users, [p.get("partner_id", "") for p in payouts], {"full_name": 1})
        for p in payouts:
            name = (pnames.get(p.get("partner_id", "")) or {}).get("full_name", "Partner")
            ref = "PO-" + str(p["_id"])[-8:].upper()
            if q and q.lower() not in (name + p.get("event_title", "") + ref).lower():
                continue
            rows.append(payout_line(p, name))
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


@api.get("/admin/ledger")
async def admin_ledger(frm: str = "", to: str = "", kind: str = "", direction: str = "all",
                       q: str = "", status: str = "", page: int = 1, limit: int = 50,
                       user: dict = Depends(require_perm("finance:view"))):
    rows = await ledger_rows(frm, to, kind, direction, q, status)
    rates = await fx_rates()

    def base(row: dict, field: str) -> float:
        return float(row.get(field) or 0) / (rates.get((row.get("currency") or BASE_CURRENCY).upper()) or 1.0)

    money_in = [r for r in rows if r["direction"] == "in"]
    paid_out = [r for r in rows if r["direction"] == "out"]
    totals = {"collected": round(sum(base(r, "gross") for r in money_in), 2),
              "commission": round(sum(base(r, "commission") for r in money_in), 2),
              "tax": round(sum(base(r, "tax") for r in money_in), 2),
              "payouts_pending": round(sum(base(r, "payout") for r in paid_out if r["status"] == "pending"), 2),
              "payouts_paid": round(sum(base(r, "payout") for r in paid_out if r["status"] == "paid"), 2),
              "entries": len(rows)}
    start = (page - 1) * limit
    return {"items": rows[start:start + limit], "total": len(rows), "page": page,
            "totals": totals, "kinds": MONEY_IN_KINDS, "currency": BASE_CURRENCY,
            "can_manage": "finance:manage" in perms_of(user)}


@api.get("/admin/ledger/export")
async def export_ledger(frm: str = "", to: str = "", kind: str = "", direction: str = "all",
                        q: str = "", status: str = "",
                        user: dict = Depends(require_perm("finance:view"))):
    """CSV that opens straight in Excel."""
    rows = await ledger_rows(frm, to, kind, direction, q, status)
    cols = ["date", "direction", "reference", "order_no", "kind_label", "client", "email",
            "description", "currency", "gross", "tax", "commission", "payout", "status", "gateway"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "") for c in cols})
    await audit(user, "ledger.export", "ledger", "", {"rows": len(rows), "from": frm, "to": to})
    stamp = now_utc().strftime("%Y%m%d-%H%M")
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="buddilio-ledger-{stamp}.csv"'})


async def invoice_doc(order: dict) -> dict:
    buyer = None
    if order.get("user_id"):
        try:
            buyer = await db.users.find_one({"_id": ObjectId(order["user_id"])},
                                            {"full_name": 1, "email": 1, "city": 1, "country": 1})
        except Exception:
            buyer = None
    paid = order.get("payment_status") == "paid"
    tpl = template_for(order["kind"])
    return {"invoice_no": invoice_no(order), "receipt_no": receipt_no(order) if paid else "",
            "order_no": order.get("order_no", ""), "issued_at": order.get("created_at", ""),
            "paid_at": order.get("paid_at", ""), "status": order.get("payment_status", ""),
            "refund_status": order.get("refund_status", "none"),
            "kind": order["kind"], "kind_label": MONEY_IN_KINDS.get(order["kind"], order["kind"]),
            "template": tpl["heading"], "line_label": tpl["line"], "note": tpl["note"],
            "seller": {"name": "Buddilio", "email": os.environ.get("SUPPORT_EMAIL", "hello@buddilio.com"),
                       "site": "buddilio.com"},
            "buyer": {"name": (buyer or {}).get("full_name", "Guest"),
                      "email": order.get("user_email", ""), "city": (buyer or {}).get("city", ""),
                      "country": (buyer or {}).get("country", "")},
            "lines": [{"description": order.get("item_name", ""), "quantity": order.get("quantity", 1),
                       "amount": round(float(order.get("subtotal") or 0), 2)}],
            "discount": round(float(order.get("discount") or 0), 2),
            "credit_applied": round(float(order.get("credit_applied") or 0), 2),
            "tax": round(float(order.get("tax") or 0), 2),
            "tax_label": order.get("tax_label", "Tax"), "tax_percent": order.get("tax_percent", 0),
            "total": round(float(order.get("total") or 0), 2),
            "commission": await commission_for(order),
            "currency": order.get("currency", BASE_CURRENCY), "gateway": order.get("gateway", ""),
            "transaction_id": order.get("transaction_id", "")}


@api.get("/orders/{oid}/invoice")
async def order_invoice(oid: str, user: dict = Depends(get_current_user)):
    """Buyers see their own invoice/receipt; finance staff can pull anyone's."""
    order = await invoice_order(oid, user)
    return await invoice_doc(order)


@api.get("/orders/{oid}/invoice.pdf")
async def order_invoice_pdf(oid: str, user: dict = Depends(get_current_user)):
    order = await invoice_order(oid, user)
    inv = await invoice_doc(order)
    conf = await currency_config()
    symbol = (conf.get(inv["currency"]) or {}).get("symbol", "")
    pdf = invoice_pdf(inv, symbol)
    name = (inv["receipt_no"] or inv["invoice_no"]) + ".pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


async def invoice_order(oid: str, user: dict) -> dict:
    try:
        order = await db.orders.find_one({"_id": ObjectId(oid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid order id")
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("user_id") != user["id"] and "finance:view" not in perms_of(user):
        raise HTTPException(status_code=403, detail="That invoice isn't yours.")
    return order


@api.get("/me/ledger")
async def my_ledger(kind: str = "", user: dict = Depends(get_current_user)):
    """Everything a member paid us, everything we owe them, and the invoice behind each line."""
    flt: dict[str, Any] = {"user_id": user["id"], "payment_status": {"$in": ["paid", "pending", "failed"]}}
    if kind and kind in MONEY_IN_KINDS:
        flt["kind"] = kind
    orders = await db.orders.find(flt).sort("created_at", -1).limit(200).to_list(200)
    payments = [{"id": str(o["_id"]), "date": o.get("paid_at") or o.get("created_at", ""),
                 "reference": invoice_no(o), "receipt": receipt_no(o) if o.get("payment_status") == "paid" else "",
                 "kind": o["kind"], "kind_label": MONEY_IN_KINDS.get(o["kind"], o["kind"]),
                 "template": template_for(o["kind"])["heading"],
                 "description": o.get("item_name", ""), "amount": round(float(o.get("total") or 0), 2),
                 "tax": round(float(o.get("tax") or 0), 2),
                 "status": o.get("refund_status") if o.get("refund_status", "none") != "none"
                           else o.get("payment_status", ""),
                 "currency": o.get("currency", BASE_CURRENCY)} for o in orders]
    credits = await db.credits.find({"user_id": user["id"]}).sort("created_at", -1).limit(100).to_list(100)
    payouts = await db.payouts.find({"partner_id": user["id"]}).sort("created_at", -1).limit(100).to_list(100)
    return {"payments": payments,
            "credits": [{"date": c.get("created_at", ""), "amount": round(float(c["amount"]), 2),
                         "reason": c.get("reason", ""), "type": c.get("type", "")} for c in credits],
            "earnings": [{"id": str(p["_id"]), "date": p.get("created_at", ""),
                          "reference": "PO-" + str(p["_id"])[-8:].upper(),
                          "description": p.get("event_title", ""), "kind": p.get("kind", "event"),
                          "gross": round(float(p.get("gross") or 0), 2),
                          "fee": round(float(p.get("fee") or 0), 2),
                          "net": round(float(p.get("net") or 0), 2), "status": p.get("status", "pending"),
                          "currency": p.get("currency", BASE_CURRENCY)} for p in payouts],
            "totals": {"paid": round(sum(p["amount"] for p in payments if p["status"] == "paid"), 2),
                       "credit_balance": await credit_balance(user["id"]),
                       "earned": round(sum(float(p.get("net") or 0) for p in payouts), 2),
                       "earned_pending": round(sum(float(p.get("net") or 0) for p in payouts
                                                   if p.get("status") == "pending"), 2)},
            "kinds": MONEY_IN_KINDS, "currency": BASE_CURRENCY}


# ---------------- SEO & indexing ----------------
def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def seo_settings() -> dict:
    return await db.seo_settings.find_one({"_id": "seo"}) or {}


def _write_key_file(key: str) -> bool:
    """IndexNow needs {key}.txt at the site root; public/ ships with every build."""
    try:
        folder = Path(__file__).resolve().parent.parent / "frontend" / "public"
        for old in folder.glob("*.txt"):
            if old.stem != "robots" and old.stem != key and len(old.stem) == 32:
                old.unlink(missing_ok=True)   # a rotated key must stop working
        (folder / f"{key}.txt").write_text(key, encoding="utf-8")
        return True
    except Exception as e:
        logger.error(f"Could not write IndexNow key file: {e}")
        return False


async def ensure_indexnow_key() -> str:
    doc = await seo_settings()
    key = doc.get("indexnow_key")
    if not key:
        key = seo.new_key()
        await db.seo_settings.update_one({"_id": "seo"}, {"$set": {"indexnow_key": key}}, upsert=True)
    _write_key_file(key)
    return key


def seo_site_url(doc: dict) -> str:
    return (doc.get("site_url") or seo_site_base()).rstrip("/")


class SeoSettingsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    gsc_verification: str = ""
    site_url: str = ""


class SeoSubmitIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scope: Literal["all", "blog", "custom"] = "all"
    urls: List[str] = []


@api.get("/seo/public")
async def seo_public():
    """Read by the build's prerender step so verification tags land in the served HTML."""
    doc = await seo_settings()
    return {"gsc_verification": doc.get("gsc_verification", ""),
            "indexnow_key": doc.get("indexnow_key", ""), "site_url": seo_site_url(doc)}


@api.get("/admin/seo")
async def admin_seo(user: dict = Depends(require_perm("content:manage"))):
    doc = await seo_settings()
    urls, _ = await _sitemap_urls()
    base = seo_site_url(doc)
    groups: dict[str, int] = {}
    for loc, _pri in urls:
        key = ("Journal" if loc.startswith("/blog") else "Events" if loc.startswith("/events")
               else "Cities" if loc.startswith("/city/") else "Pages" if loc.startswith("/p/")
               else "Core")
        groups[key] = groups.get(key, 0) + 1
    key = doc.get("indexnow_key", "")
    return {"site_url": base, "sitemap_url": f"{base}/api/sitemap.xml",
            "robots_url": f"{base}/robots.txt",
            "gsc_verification": doc.get("gsc_verification", ""),
            "indexnow_key": key, "key_file_url": f"{base}/{key}.txt" if key else "",
            "total": len(urls), "groups": groups,
            "urls": [loc for loc, _p in urls][:400],
            "last_submit": doc.get("last_submit") or None,
            "can_submit": bool(base) and "localhost" not in base and ".preview." not in base}


@api.put("/admin/seo")
async def admin_seo_save(payload: SeoSettingsIn, user: dict = Depends(require_perm("content:manage"))):
    tag = payload.gsc_verification.strip()
    if tag and "content=" in tag:  # accept the full <meta> tag and keep only the token
        m = re.search(r'content=["\']([^"\']+)["\']', tag)
        tag = m.group(1) if m else tag
    site = payload.site_url.strip().rstrip("/")
    if site and not site.startswith("http"):
        site = f"https://{site}"
    await db.seo_settings.update_one({"_id": "seo"},
                                    {"$set": {"gsc_verification": tag[:200], "site_url": site[:200]}},
                                    upsert=True)
    await audit(user, "seo.settings", "seo", "seo", {"site_url": site, "verification": bool(tag)})
    return {"ok": True, "message": "SEO settings saved. Republish the site to put them in the HTML."}


@api.post("/admin/seo/indexnow-key")
async def admin_seo_rotate_key(user: dict = Depends(require_perm("content:manage"))):
    key = seo.new_key()
    await db.seo_settings.update_one({"_id": "seo"}, {"$set": {"indexnow_key": key}}, upsert=True)
    written = _write_key_file(key)
    await audit(user, "seo.indexnow_key", "seo", "seo", {})
    return {"ok": True, "indexnow_key": key, "key_file_written": written,
            "message": "New IndexNow key created. Republish so the key file goes live."}


@api.post("/admin/seo/submit")
async def admin_seo_submit(payload: SeoSubmitIn, user: dict = Depends(require_perm("content:manage"))):
    doc = await seo_settings()
    base = seo_site_url(doc)
    if not base or "localhost" in base or ".preview." in base:
        raise HTTPException(status_code=400,
                            detail="Set your live site address (e.g. https://buddilio.com) first — "
                                   "search engines can't crawl the preview.")
    key = await ensure_indexnow_key()
    if payload.scope == "custom":
        paths = [u.strip() for u in payload.urls if u.strip()][:200]
    else:
        urls, _ = await _sitemap_urls()
        paths = [loc for loc, _p in urls if payload.scope == "all" or loc.startswith("/blog")]
    targets = [p if p.startswith("http") else f"{base}{p if p.startswith('/') else '/' + p}"
               for p in paths]
    if not targets:
        raise HTTPException(status_code=400, detail="Nothing to submit.")
    results = await seo.submit(base, key, targets)
    record = {"at": iso(now_utc()), "count": len(targets), "scope": payload.scope,
              "by": user.get("email", ""), "results": results}
    await db.seo_settings.update_one({"_id": "seo"}, {"$set": {"last_submit": record}}, upsert=True)
    await audit(user, "seo.submit", "seo", "seo", {"count": len(targets), "scope": payload.scope})
    ok = sum(1 for r in results if r["ok"])
    return {"ok": ok > 0, "submitted": len(targets), "results": results,
            "message": (f"{len(targets)} URLs sent to {ok} of {len(results)} endpoints."
                        if ok else "Search engines rejected the submission — check the details below.")}


# ---------------- human support inbox ----------------
async def _support_thread(tid: str, token: str = "", user: Optional[dict] = None) -> dict:
    doc = await db.support_threads.find_one({"_id": as_oid(tid, "conversation")})
    if not doc:
        raise HTTPException(status_code=404, detail="That conversation no longer exists.")
    owned = (user and doc.get("user_id") == user["id"]) or (token and doc.get("token") == token)
    if not owned:
        raise HTTPException(status_code=403, detail="That conversation isn't yours.")
    return doc


@api.post("/support/threads")
async def support_start(payload: support.StartIn, request: Request,
                       user: Optional[dict] = Depends(optional_user)):
    """Escalates a chat to a human. Guests identify themselves with a name and email."""
    name = (user.get("full_name") if user else payload.name.strip())[:80]
    email = (user.get("email") if user else payload.email.strip().lower())[:160]
    if not user:
        if not name or "@" not in email:
            raise HTTPException(status_code=400, detail="Please add your name and email so we can reply.")
        ip = botguard.client_ip(request)
        recent = await db.support_threads.count_documents({"ip": ip, "created_at": {"$gte": iso(
            now_utc() - timedelta(hours=1))}})
        if recent >= 5:
            raise HTTPException(status_code=429, detail="That's a lot of chats. Please try again later.")
    token = support.new_token()
    first = support.message("visitor", payload.message, name)
    doc = {"user_id": user["id"] if user else "", "name": name, "email": email,
           "subject": (payload.subject.strip() or payload.message.strip())[:120],
           "page": payload.page[:200], "status": "open", "token": token,
           "ip": "" if user else botguard.client_ip(request),
           "ai_transcript": [str(t)[:1000] for t in payload.ai_transcript][:6],
           "messages": [first], "unread_for_staff": True, "unread_for_visitor": False,
           "created_at": iso(now_utc()), "updated_at": iso(now_utc())}
    res = await db.support_threads.insert_one(doc)
    doc["_id"] = res.inserted_id
    return {"thread": support.public_thread(doc), "token": token}


@api.get("/support/threads/{tid}")
async def support_get(tid: str, token: str = "", user: Optional[dict] = Depends(optional_user)):
    doc = await _support_thread(tid, token, user)
    if doc.get("unread_for_visitor"):
        await db.support_threads.update_one({"_id": doc["_id"]}, {"$set": {"unread_for_visitor": False}})
    return {"thread": support.public_thread(doc)}


@api.get("/support/threads")
async def support_mine(user: dict = Depends(get_current_user)):
    rows = await db.support_threads.find({"user_id": user["id"]}).sort("updated_at", -1).limit(20).to_list(20)
    return {"items": [support.public_thread(r) | {"unread": bool(r.get("unread_for_visitor"))} for r in rows]}


@api.post("/support/threads/{tid}/messages")
async def support_reply(tid: str, payload: support.ReplyIn,
                        user: Optional[dict] = Depends(optional_user)):
    doc = await _support_thread(tid, payload.token, user)
    if doc.get("status") == "closed":
        await db.support_threads.update_one({"_id": doc["_id"]}, {"$set": {"status": "open"}})
    msg = support.message("visitor", payload.message, doc.get("name", ""))
    await db.support_threads.update_one({"_id": doc["_id"]}, {
        "$push": {"messages": {"$each": [msg], "$slice": -support.MAX_MESSAGES}},
        "$set": {"unread_for_staff": True, "updated_at": iso(now_utc())}})
    return {"ok": True, "message": msg}


@api.get("/admin/support")
async def admin_support_list(status: str = "", q: str = "",
                             user: dict = Depends(require_perm("support:respond"))):
    query: dict = {}
    if status in support.STATUSES:
        query["status"] = status
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"name": rx}, {"email": rx}, {"subject": rx}]
    rows = await db.support_threads.find(query).sort("updated_at", -1).limit(200).to_list(200)
    counts = {s: await db.support_threads.count_documents({"status": s}) for s in support.STATUSES}
    counts["unread"] = await db.support_threads.count_documents({"unread_for_staff": True})
    return {"items": [support.staff_card(r) for r in rows], "counts": counts}


@api.get("/admin/support/{tid}")
async def admin_support_get(tid: str, user: dict = Depends(require_perm("support:respond"))):
    doc = await db.support_threads.find_one({"_id": as_oid(tid, "conversation")})
    if not doc:
        raise HTTPException(status_code=404, detail="That conversation no longer exists.")
    await db.support_threads.update_one({"_id": doc["_id"]}, {"$set": {"unread_for_staff": False}})
    return {"thread": support.staff_card(doc) | support.public_thread(doc),
            "ai_transcript": doc.get("ai_transcript", [])}


@api.post("/admin/support/{tid}/reply")
async def admin_support_reply(tid: str, payload: support.ReplyIn,
                             user: dict = Depends(require_perm("support:respond"))):
    doc = await db.support_threads.find_one({"_id": as_oid(tid, "conversation")})
    if not doc:
        raise HTTPException(status_code=404, detail="That conversation no longer exists.")
    msg = support.message("staff", payload.message, first_name(user.get("full_name")) or "Buddilio")
    await db.support_threads.update_one({"_id": doc["_id"]}, {
        "$push": {"messages": {"$each": [msg], "$slice": -support.MAX_MESSAGES}},
        "$set": {"unread_for_visitor": True, "unread_for_staff": False, "status": "pending",
                 "updated_at": iso(now_utc())}})
    if doc.get("user_id"):
        await notify(doc["user_id"], "Buddilio support replied", payload.message[:180],
                     "system", "/dashboard", cta="Read the reply")
    elif doc.get("email"):
        await send_email(doc["email"], "Buddilio support replied to you",
                         wrap("We've replied", f"<p>{payload.message[:900]}</p>"
                              "<p>Open Buddilio and click Ask Buddy — your conversation is waiting there.</p>",
                              "Open Buddilio", site_base()))
    await audit(user, "support.reply", "support_thread", tid, {})
    return {"ok": True, "message": "Reply sent."}


@api.patch("/admin/support/{tid}")
async def admin_support_status(tid: str, body: dict,
                              user: dict = Depends(require_perm("support:respond"))):
    status = str(body.get("status", "")).lower()
    if status not in support.STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status.")
    doc = await db.support_threads.find_one_and_update(
        {"_id": as_oid(tid, "conversation")},
        {"$set": {"status": status, "updated_at": iso(now_utc())}})
    if not doc:
        raise HTTPException(status_code=404, detail="That conversation no longer exists.")
    await audit(user, "support.status", "support_thread", tid, {"status": status})
    return {"ok": True, "message": f"Conversation marked {status}."}


import vendor_routes

vendor_routes.register({
    "api": api, "db": db, "clean": clean, "audit": audit, "require_perm": require_perm,
    "get_current_user": get_current_user, "notify": notify, "send_tpl": send_tpl,
    "first_name": first_name, "perms_of": perms_of, "Response": Response,
    "site_url": lambda: FRONTEND_URL,
    "fx_rates": fx_rates, "base_currency": BASE_CURRENCY,
})

app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    loaded = await vault.load_into_env(db)
    if loaded:
        logger.info(f"credential overrides loaded from the dashboard: {loaded}")
    if not await db.countries.count_documents({}):
        await db.countries.insert_many([dict(c) | {"created_at": iso(now_utc())} for c in COUNTRY_SEED])
    await db.countries.create_index("code", unique=True)
    await refresh_countries()
    await db.users.create_index("email", unique=True)
    await db.users.create_index([("city", 1), ("role", 1)])
    await db.events.create_index([("status", 1), ("starts_at", 1)])
    await db.events.create_index([("city", 1), ("category", 1)])
    await db.event_participants.create_index([("event_id", 1), ("user_id", 1)])
    await db.messages.create_index([("conversation_id", 1), ("created_at", 1)])
    await db.notifications.create_index([("user_id", 1), ("read", 1)])
    await db.orders.create_index([("user_id", 1), ("created_at", -1)])
    try:
        await db.payouts.drop_index("event_id_1")
    except Exception:
        pass
    await db.payouts.create_index("event_id", unique=True,
                                  partialFilterExpression={"event_id": {"$gt": ""}})
    await db.reviews.create_index([("event_id", 1), ("user_id", 1)], unique=True)
    await db.push_subscriptions.create_index("endpoint", unique=True)
    await db.city_waitlist.create_index([("city", 1), ("email", 1)], unique=True)
    await db.prizes.create_index("month", unique=True)
    await db.push_subscriptions.create_index("user_id")
    await db.referrals.create_index("invitee_id", unique=True)
    await db.referrals.create_index("referrer_id")
    await db.credits.create_index([("user_id", 1), ("created_at", -1)])
    await db.users.create_index("referral_code", sparse=True)
    await db.ai_messages.create_index([("user_id", 1), ("session_id", 1), ("created_at", 1)])
    await db.ai_guest_asks.create_index([("ip", 1), ("created_at", -1)])
    await db.ai_picks.create_index("user_id", unique=True)
    await db.ai_matches.create_index([("user_id", 1), ("event_id", 1)], unique=True)
    await db.files.create_index("storage_path")
    await db.files.create_index([("owner_id", 1), ("created_at", -1)])
    await db.vendor_invites.create_index("token", unique=True)
    await db.vendor_invites.create_index([("manager_id", 1), ("created_at", -1)])
    await db.ai_drafts.create_index([("user_id", 1), ("created_at", -1)])
    await db.event_photos.create_index([("event_id", 1), ("created_at", -1)])
    await db.event_photos.create_index([("event_id", 1), ("user_id", 1)])
    await db.payout_reminders.create_index([("manager_id", 1), ("week", 1)], unique=True)
    await db.host_follows.create_index([("user_id", 1), ("host_id", 1)], unique=True)
    await db.host_follows.create_index("host_id")
    await db.event_recaps.create_index("event_id", unique=True)
    await db.cms_pages.create_index("slug", unique=True)
    await db.site_content.create_index("key", unique=True)
    await db.city_guides.create_index("slug", unique=True)
    await db.vendor_commission_invoices.create_index([("vendor_id", 1), ("period", 1)], unique=True)
    await db.vendor_commission_invoices.create_index("invoice_no", unique=True)
    await db.vendor_payout_batches.create_index([("status", 1), ("created_at", -1)])
    await db.email_templates.create_index("key", unique=True)
    await db.companion_bookings.create_index([("member_id", 1), ("created_at", -1)])
    await db.companion_bookings.create_index([("companion_id", 1), ("status", 1)])
    await db.users.create_index("companion.status")
    await db.upload_parts.create_index([("upload_id", 1), ("index", 1)], unique=True)
    await db.upload_sessions.create_index("upload_id", unique=True)
    await db.upload_sessions.create_index("created_at", expireAfterSeconds=3600)
    await db.login_attempts.create_index("identifier")
    await db.support_threads.create_index([("status", 1), ("updated_at", -1)])
    await db.support_threads.create_index("token")
    await db.support_threads.create_index("user_id")
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    admin_email = os.environ["ADMIN_EMAIL"]
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "full_name": "Buddilio Admin", "email": admin_email,
            "password_hash": hash_password(os.environ["ADMIN_PASSWORD"]), "role": "admin",
            "staff_role": "super_admin",
            "status": "active", "city": "Delhi NCR", "age": 35, "photo": "", "bio": "",
            "interests": [], "event_categories": [], "blocked": [], "connections": [],
            "saved_events": [], "verified": True, "created_at": iso(now_utc())})
    elif not verify_password(os.environ["ADMIN_PASSWORD"], existing.get("password_hash", "")):
        await db.users.update_one({"_id": existing["_id"]},
                                  {"$set": {"password_hash": hash_password(os.environ["ADMIN_PASSWORD"])}})
    if existing and not existing.get("staff_role"):
        await db.users.update_one({"_id": existing["_id"]}, {"$set": {"staff_role": "super_admin"}})
    asyncio.create_task(reminder_loop())
    asyncio.create_task(payout_loop())
    try:
        await asyncio.to_thread(init_storage)
        logger.info("Object storage initialised")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    client.close()
