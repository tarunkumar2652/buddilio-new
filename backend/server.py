from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import asyncio
import jwt
import bcrypt
import uuid
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Annotated, Any

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, Query, WebSocket, WebSocketDisconnect, UploadFile, File, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from pydantic import BaseModel, Field, BeforeValidator, EmailStr, ConfigDict

from emailer import send_email, wrap
from realtime import hub
from push import push_to, push_enabled, vapid_public_key
from storage import init_storage, put_object, get_object, MIME_TYPES, APP_NAME
from city_guides import guide_for

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


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {"sub": user_id, "email": email, "role": role,
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


async def audit(actor: dict, action: str, entity: str, entity_id: str = "", meta: dict | None = None):
    await db.audit_logs.insert_one({
        "actor_id": actor["id"], "actor_email": actor.get("email"), "action": action,
        "entity": entity, "entity_id": entity_id, "meta": meta or {}, "created_at": iso(now_utc()),
    })


FRONTEND_URL = os.environ.get("FRONTEND_URL", "")

BASE_CURRENCY = os.environ.get("BASE_CURRENCY", "INR")

DEFAULT_CURRENCIES = {
    "INR": {"rate": 1.0, "symbol": "₹", "label": "Indian Rupee", "stripe_min": 4200},
    "USD": {"rate": 0.012, "symbol": "$", "label": "US Dollar", "stripe_min": 50},
    "EUR": {"rate": 0.011, "symbol": "€", "label": "Euro", "stripe_min": 50},
    "GBP": {"rate": 0.0094, "symbol": "£", "label": "British Pound", "stripe_min": 30},
    "AED": {"rate": 0.044, "symbol": "AED ", "label": "UAE Dirham", "stripe_min": 200},
    "SGD": {"rate": 0.016, "symbol": "S$", "label": "Singapore Dollar", "stripe_min": 50},
    "CAD": {"rate": 0.016, "symbol": "C$", "label": "Canadian Dollar", "stripe_min": 50},
    "AUD": {"rate": 0.018, "symbol": "A$", "label": "Australian Dollar", "stripe_min": 50},
    "THB": {"rate": 0.39, "symbol": "฿", "label": "Thai Baht", "stripe_min": 1000},
    "JPY": {"rate": 1.8, "symbol": "¥", "label": "Japanese Yen", "stripe_min": 50},
}
ZERO_DECIMAL = {"JPY", "KRW"}

# Buddilio operates city by city. Each country carries its own currency and tax treatment.
COUNTRIES = [
    {"code": "IN", "name": "India", "currency": "INR", "tax_percent": 18, "tax_label": "GST",
     "emergency": "112", "cities": ["Delhi NCR", "Gurugram", "Noida", "Mumbai", "Bengaluru", "Hyderabad", "Pune", "Goa"]},
    {"code": "AE", "name": "United Arab Emirates", "currency": "AED", "tax_percent": 5, "tax_label": "VAT",
     "emergency": "999", "cities": ["Dubai", "Abu Dhabi"]},
    {"code": "SG", "name": "Singapore", "currency": "SGD", "tax_percent": 9, "tax_label": "GST",
     "emergency": "999", "cities": ["Singapore"]},
    {"code": "GB", "name": "United Kingdom", "currency": "GBP", "tax_percent": 20, "tax_label": "VAT",
     "emergency": "999", "cities": ["London", "Manchester"]},
    {"code": "US", "name": "United States", "currency": "USD", "tax_percent": 8.875, "tax_label": "Sales tax",
     "emergency": "911", "cities": ["New York", "Los Angeles", "Miami", "Austin"]},
    {"code": "CA", "name": "Canada", "currency": "CAD", "tax_percent": 13, "tax_label": "HST",
     "emergency": "911", "cities": ["Toronto", "Vancouver"]},
    {"code": "AU", "name": "Australia", "currency": "AUD", "tax_percent": 10, "tax_label": "GST",
     "emergency": "000", "cities": ["Sydney", "Melbourne"]},
    {"code": "DE", "name": "Germany", "currency": "EUR", "tax_percent": 19, "tax_label": "VAT",
     "emergency": "112", "cities": ["Berlin"]},
    {"code": "ES", "name": "Spain", "currency": "EUR", "tax_percent": 21, "tax_label": "VAT",
     "emergency": "112", "cities": ["Barcelona", "Madrid"]},
    {"code": "FR", "name": "France", "currency": "EUR", "tax_percent": 20, "tax_label": "VAT",
     "emergency": "112", "cities": ["Paris"]},
    {"code": "TH", "name": "Thailand", "currency": "THB", "tax_percent": 7, "tax_label": "VAT",
     "emergency": "191", "cities": ["Bangkok"]},
    {"code": "JP", "name": "Japan", "currency": "JPY", "tax_percent": 10, "tax_label": "Consumption tax",
     "emergency": "110", "cities": ["Tokyo"]},
]
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
REFERRAL_REWARD = float(os.environ.get("REFERRAL_REWARD", "250"))


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
        greeting = f"<p>Hi {user.get('full_name', 'there').split(' ')[0]},</p><p>{body}</p>"
        html = wrap(title, greeting, cta or ("Open Buddilio" if link else ""),
                    f"{FRONTEND_URL}{link}" if link else "")
        await send_email(user["email"], f"{title} · Buddilio", html)


async def membership_active(user_id: str) -> Optional[dict]:
    m = await db.user_memberships.find_one(
        {"user_id": user_id, "status": "active", "ends_at": {"$gt": iso(now_utc())}},
        sort=[("ends_at", -1)])
    return clean(m) if m else None


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
    docs = await db.credits.find({"user_id": user_id}, {"amount": 1}).to_list(500)
    return round(sum(d["amount"] for d in docs), 2)


BADGES = [(10, "Legend"), (5, "Ambassador"), (3, "Connector"), (1, "Starter")]


def badge_for(count: int) -> dict:
    """Lifetime rewarded invites decide the badge; `next` is the invites needed for the following tier."""
    nxt = next((n for n, _ in reversed(BADGES) if n > count), 0)
    for need, name in BADGES:
        if count >= need:
            return {"name": name, "at": need, "next": nxt}
    return {"name": "", "at": 0, "next": 1}


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
                 f"You earn ₹{REFERRAL_REWARD:.0f} credit on their first paid booking.",
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
    password: str = Field(min_length=6)
    dob: str
    gender: str
    city: str
    bio: str = ""
    photo: str = ""
    interests: List[str] = []
    event_categories: List[str] = []
    lifestyle: List[str] = []
    is_adult: bool = False
    accept_terms: bool = False
    role: str = "user"
    org_name: str = ""
    country: str = ""
    referral_code: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionIn(BaseModel):
    session_id: str


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
    kind: str  # membership | product | event
    item_id: str
    quantity: int = 1
    coupon_code: str = ""
    currency: str = "INR"
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
    body: str


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


@api.post("/auth/register")
async def register(payload: RegisterIn, response: Response):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    age = age_from_dob(payload.dob)
    if age < 21:
        raise HTTPException(status_code=400, detail="You must be at least 21 years old to join Buddilio.")
    if not payload.is_adult or not payload.accept_terms:
        raise HTTPException(status_code=400, detail="Please confirm your age and accept the policies.")
    if len(payload.mobile.strip()) < 8:
        raise HTTPException(status_code=400, detail="Please enter a valid mobile number.")
    role = "partner" if payload.role == "partner" else "user"
    doc = {
        "full_name": payload.full_name, "email": email, "mobile": payload.mobile,
        "password_hash": hash_password(payload.password), "role": role, "status": "active",
        "dob": payload.dob, "age": age, "gender": payload.gender, "city": payload.city,
        "bio": payload.bio, "photo": payload.photo, "interests": payload.interests,
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
    await register_referral(payload.referral_code, uid, payload.full_name)
    await notify(uid, "Welcome to Buddilio", "Complete your profile to get better companion matches.", "registration", "/profile")
    await send_email(email, "Welcome to Buddilio", wrap(
        f"Welcome to Buddilio, {payload.full_name.split(' ')[0]}",
        "<p>Your account is live. Here's how members get the most out of Buddilio:</p>"
        "<p><b>1.</b> Finish your profile so we can match you with the right companions.<br/>"
        "<b>2.</b> Browse curated experiences in your city.<br/>"
        "<b>3.</b> Message a member, then pick a night out together.</p>"
        "<p>Remember: always meet in public venues and never send money to another member.</p>",
        "Open my dashboard", f"{FRONTEND_URL}/dashboard"))
    token = create_access_token(uid, email, role)
    set_cookies(response, token)
    user = clean(await db.users.find_one({"_id": res.inserted_id}))
    return {"access_token": token, "user": user}


@api.post("/auth/login")
async def login(payload: LoginIn, request: Request, response: Response):
    email = payload.email.lower().strip()
    ident = f"email:{email}"
    att = await db.login_attempts.find_one({"identifier": ident})
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
    token = create_access_token(str(user["_id"]), email, user.get("role", "user"))
    set_cookies(response, token)
    return {"access_token": token, "user": clean(user)}


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    user["membership"] = await membership_active(user["id"])
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
        html = wrap("Reset your Buddilio password",
                    f"<p>Hi {user.get('full_name','there').split(' ')[0]},</p>"
                    "<p>We received a request to reset your Buddilio password. "
                    "This link expires in one hour and can only be used once.</p>"
                    "<p>If you didn't ask for this, you can safely ignore this email.</p>",
                    "Choose a new password", f"{FRONTEND_URL}/reset-password?token={token}")
        await send_email(user["email"], "Reset your Buddilio password", html)
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


@api.post("/auth/google/session")
async def google_session(payload: GoogleSessionIn, response: Response):
    import httpx
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                        headers={"X-Session-ID": payload.session_id})
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Google sign-in failed. Please try again.")
    data = r.json()
    email = (data.get("email") or "").lower()
    user = await db.users.find_one({"email": email})
    if not user:
        doc = {
            "full_name": data.get("name") or email.split("@")[0], "email": email, "mobile": "",
            "password_hash": hash_password(secrets.token_urlsafe(16)), "role": "user", "status": "active",
            "dob": "", "age": 0, "gender": "", "city": "Delhi NCR", "bio": "",
            "photo": data.get("picture") or "", "interests": [], "event_categories": [], "lifestyle": [],
            "verified": True, "email_verified": True, "auth_provider": "google",
            "privacy": {"profile_visibility": "public", "who_can_message": "everyone"},
            "notification_prefs": {"email": True, "in_app": True, "sms": False},
            "blocked": [], "connections": [], "saved_events": [], "created_at": iso(now_utc()),
        }
        res = await db.users.insert_one(doc)
        user = await db.users.find_one({"_id": res.inserted_id})
    token = create_access_token(str(user["_id"]), email, user.get("role", "user"))
    set_cookies(response, token)
    return {"access_token": token, "user": clean(user)}


# ---------------- profiles / discover ----------------
@api.put("/users/me")
async def update_me(payload: ProfileIn, user: dict = Depends(get_current_user)):
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
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
    items = []
    for d in await cur.to_list(limit):
        c = clean(d)
        c["membership"] = bool(await membership_active(c["id"]))
        items.append(c)
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
                      page: int = 1, limit: int = 12):
    flt: dict[str, Any] = {"status": "published"}
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
    items = []
    for d in docs:
        e = clean(d)
        if e.get("rating_count"):
            top = await db.reviews.find_one(
                {"event_id": e["id"], "status": {"$ne": "hidden"}, "comment": {"$nin": ["", None]}},
                sort=[("rating", -1), ("created_at", -1)])
            if top:
                u = await db.users.find_one({"_id": ObjectId(top["user_id"])}, {"full_name": 1})
                e["top_review"] = {"rating": top["rating"], "comment": top["comment"][:160],
                                   "user_name": (u["full_name"] if u else "Member").split(" ")[0]}
        items.append(e)
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
    parts = await db.event_participants.find({"event_id": event_id, "status": "confirmed"}).to_list(200)
    revs = await db.reviews.find({"event_id": event_id, "status": {"$ne": "hidden"}}, {"rating": 1}).to_list(500)
    ev["rating"] = round(sum(r["rating"] for r in revs) / len(revs), 2) if revs else 0
    ev["rating_count"] = len(revs)
    ev["participants"] = []
    for p in parts[:20]:
        u = await db.users.find_one({"_id": ObjectId(p["user_id"])},
                                    {"full_name": 1, "photo": 1, "city": 1})
        if u:
            ev["participants"].append(clean(u))
    ev["participant_count"] = len(parts)
    ev["seats_left"] = max(ev.get("capacity", 0) - len(parts), 0)
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
    parts = await db.event_participants.find({"user_id": user["id"]}).to_list(200)
    out = []
    for p in parts:
        try:
            ev = await db.events.find_one({"_id": ObjectId(p["event_id"])})
        except Exception:
            continue
        if ev:
            e = clean(ev)
            e["my_status"] = p["status"]
            out.append(e)
    return {"items": out}


@api.get("/me/saved-events")
async def saved_events(user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"_id": ObjectId(user["id"])})
    ids = [ObjectId(i) for i in u.get("saved_events", [])]
    docs = await db.events.find({"_id": {"$in": ids}}).to_list(100)
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
    docs = await db.events.find({"partner_id": user["id"]}).sort([("created_at", -1)]).to_list(200)
    return {"items": [clean(d) for d in docs]}


@api.get("/partner/stats")
async def partner_stats(user: dict = Depends(partner_only)):
    evs = await db.events.find({"partner_id": user["id"]}).to_list(500)
    ids = [str(e["_id"]) for e in evs]
    parts = await db.event_participants.count_documents({"event_id": {"$in": ids}})
    orders = await db.orders.find({"ref_id": {"$in": ids}, "payment_status": "paid"}).to_list(1000)
    revenue = sum(o.get("total", 0) for o in orders)
    payouts = await db.payouts.find({"partner_id": user["id"]}).to_list(500)
    revs = await db.reviews.find({"partner_id": user["id"], "status": {"$ne": "hidden"}}, {"rating": 1}).to_list(2000)
    return {"events": len(evs), "published": sum(1 for e in evs if e.get("status") == "published"),
            "pending": sum(1 for e in evs if e.get("status") == "submitted"),
            "completed": sum(1 for e in evs if e.get("status") == "completed"),
            "participants": parts, "revenue": revenue,
            "payout_due": round(sum(p["net"] for p in payouts if p["status"] == "pending"), 2),
            "payout_paid": round(sum(p["net"] for p in payouts if p["status"] == "paid"), 2),
            "rating": round(sum(r["rating"] for r in revs) / len(revs), 2) if revs else 0,
            "rating_count": len(revs)}


@api.get("/partner/events/{event_id}/participants")
async def event_participants(event_id: str, user: dict = Depends(partner_only)):
    ev = await db.events.find_one({"_id": ObjectId(event_id)})
    if not ev or (user["role"] != "admin" and ev.get("partner_id") != user["id"]):
        raise HTTPException(status_code=404, detail="Event not found")
    parts = await db.event_participants.find({"event_id": event_id}).to_list(500)
    out = []
    for p in parts:
        u = await db.users.find_one({"_id": ObjectId(p["user_id"])}, {"full_name": 1, "email": 1, "city": 1, "photo": 1})
        if u:
            item = clean(u)
            item["participation_status"] = p["status"]
            out.append(item)
    return {"items": out}


# ---------------- membership / products / coupons ----------------
@api.get("/plans")
async def plans():
    docs = await db.membership_plans.find({"active": True}).sort([("price", 1)]).to_list(50)
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
    docs = await db.products.find(flt).to_list(100)
    return {"items": [clean(d) for d in docs]}


@api.get("/me/membership")
async def my_membership(user: dict = Depends(get_current_user)):
    return {"membership": await membership_active(user["id"])}


async def price_for(kind: str, item_id: str):
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
    if member and payload.kind in ("product", "event"):
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

    currency = (payload.currency or BASE_CURRENCY).upper()
    rates = await fx_rates()
    if currency not in rates:
        raise HTTPException(status_code=400, detail="We don't support that currency yet.")
    tax_pct, tax_label = tax_for(currency, tax_pct, user.get("country_code", ""))
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
    await db.orders.update_one({"_id": order["_id"]},
                               {"$set": {"payment_status": "failed", "order_status": "failed",
                                         "failure_reason": reason}})
    await db.payments.insert_one({"order_id": str(order["_id"]), "user_id": order["user_id"],
                                  "amount": order["total"], "status": "failed", "reason": reason,
                                  "created_at": iso(now_utc())})


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
    if order.get("credit_applied", 0) > 0:
        await db.credits.update_one(
            {"order_id": str(order["_id"]), "type": "spent"},
            {"$setOnInsert": {"user_id": uid, "amount": -float(order["credit_applied"]), "type": "spent",
                              "reason": f"Credit applied to order #{order['order_no']}",
                              "order_id": str(order["_id"]), "created_at": iso(now_utc())}},
            upsert=True)
    await award_referral(uid, order)
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
            await send_email(u["email"], "Your Buddilio membership is active", wrap(
                f"{plan['name']} is live", receipt +
                f"<p>Valid until <b>{ends.strftime('%d %b %Y')}</b>. Member pricing is applied automatically at checkout.</p>",
                "See member benefits", f"{FRONTEND_URL}/membership"))
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
            await send_email(u["email"], f"You're going to {ev['title']}", wrap(
                "Booking confirmed", receipt +
                f"<p><b>When:</b> {starts.strftime('%a %d %b %Y, %I:%M %p')}<br/>"
                f"<b>Where:</b> {ev.get('venue','')}, {ev['city']}<br/>"
                f"<b>Host:</b> {ev.get('partner_name','Buddilio')}</p>"
                f"<p><b>Cancellation:</b> {ev.get('cancellation_policy','')}</p>"
                "<p>Your paid-ticket group chat is now open — say hi before the night.</p>",
                "Open event", f"{FRONTEND_URL}/events/{order['ref_id']}"))
    else:
        await notify(uid, "Purchase successful", f"{order['item_name']} is now in your account.",
                     "order", "/orders", email=False)
        u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1})
        if u:
            await send_email(u["email"], "Your Buddilio purchase", wrap(
                "Purchase confirmed", receipt + "<p>You can view this any time under My Orders.</p>",
                "View my orders", f"{FRONTEND_URL}/orders"))
    return clean(await db.orders.find_one({"_id": order["_id"]}))


@api.get("/payments/config")
async def payment_config():
    kid = os.environ.get("RAZORPAY_KEY_ID", "")
    conf = await currency_config()
    return {"razorpay_live": bool(kid and razorpay_client()), "razorpay_key_id": kid,
            "stripe_enabled": bool(os.environ.get("STRIPE_API_KEY")),
            "base_currency": "INR", "currencies": [{"code": k, **v} for k, v in conf.items()],
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
    """Simulation path — used until live Razorpay keys are configured."""
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


@api.get("/me/orders")
async def my_orders(user: dict = Depends(get_current_user)):
    docs = await db.orders.find({"user_id": user["id"]}).sort([("created_at", -1)]).to_list(200)
    return {"items": [clean(d) for d in docs]}


# ---------------- referrals / credit / push ----------------
@api.get("/me/referrals")
async def my_referrals(user: dict = Depends(get_current_user)):
    doc = await db.users.find_one({"_id": ObjectId(user["id"])})
    code = await ensure_ref_code(doc)
    invites = [{"name": r.get("invitee_name", ""), "status": r["status"],
                "created_at": r["created_at"], "rewarded_at": r.get("rewarded_at", "")}
               for r in await db.referrals.find({"referrer_id": user["id"]}).sort([("created_at", -1)]).to_list(200)]
    credits = [clean(c) for c in await db.credits.find({"user_id": user["id"]}).sort([("created_at", -1)]).to_list(100)]
    rewarded = sum(1 for i in invites if i["status"] == "rewarded")
    return {"code": code, "link": f"{FRONTEND_URL}/register?ref={code}", "reward": REFERRAL_REWARD,
            "balance": await credit_balance(user["id"]), "invites": invites, "credits": credits,
            "joined": len(invites), "rewarded": rewarded, "badge": badge_for(rewarded)}


@api.get("/referrals/leaderboard")
async def referral_leaderboard(month: str = "", user: dict = Depends(get_current_user)):
    month = (month or now_utc().strftime("%Y-%m"))[:7]
    docs = await db.referrals.find({"status": "rewarded",
                                    "rewarded_at": {"$regex": f"^{month}"}},
                                   {"referrer_id": 1}).to_list(5000)
    tally: dict[str, int] = {}
    for d in docs:
        tally[d["referrer_id"]] = tally.get(d["referrer_id"], 0) + 1
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    rows = []
    for i, (uid, count) in enumerate(ranked[:10]):
        try:
            u = await db.users.find_one({"_id": ObjectId(uid)}, {"full_name": 1, "photo": 1, "city": 1})
        except Exception:
            u = None
        lifetime = await db.referrals.count_documents({"referrer_id": uid, "status": "rewarded"})
        rows.append({"rank": i + 1, "name": short_name((u or {}).get("full_name", "")),
                     "photo": (u or {}).get("photo", ""), "city": (u or {}).get("city", ""),
                     "invites": count, "credit": round(count * REFERRAL_REWARD, 2),
                     "badge": badge_for(lifetime)["name"], "me": uid == user["id"]})
    mine = tally.get(user["id"], 0)
    lifetime = await db.referrals.count_documents({"referrer_id": user["id"], "status": "rewarded"})
    champ = await db.prizes.find_one({"month": last_month()})
    return {"month": month, "items": rows, "reward": REFERRAL_REWARD, "prize": PRIZE_LABEL,
            "me": {"rank": next((i + 1 for i, (uid, _) in enumerate(ranked) if uid == user["id"]), 0),
                   "invites": mine, "lifetime": lifetime,
                   "credit": round(mine * REFERRAL_REWARD, 2), "badge": badge_for(lifetime)},
            "champion": {"month": champ["month"], "month_label": month_label(champ["month"]),
                         "name": champ["name"], "city": champ.get("city", ""),
                         "photo": champ.get("photo", ""), "invites": champ["invites"],
                         "prize": champ.get("prize", PRIZE_LABEL),
                         "me": champ["user_id"] == user["id"]} if champ else None,
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
    docs = await db.conversations.find({"members": user["id"]}).sort([("updated_at", -1)]).to_list(100)
    out = []
    for d in docs:
        c = clean(d)
        if c["type"] == "direct":
            oid = next((m for m in c["members"] if m != user["id"]), None)
            other = await db.users.find_one({"_id": ObjectId(oid)}, {"full_name": 1, "photo": 1}) if oid else None
            c["title"] = other["full_name"] if other else "Buddilio member"
            c["avatar"] = other.get("photo", "") if other else ""
            c["other_id"] = oid
        c["unread"] = await db.messages.count_documents(
            {"conversation_id": c["id"], "sender_id": {"$ne": user["id"]}, "read": False})
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
    docs = await db.messages.find({"conversation_id": cid}).sort([("created_at", 1)]).to_list(500)
    out = []
    for d in docs:
        m = clean(d)
        u = await db.users.find_one({"_id": ObjectId(m["sender_id"])}, {"full_name": 1, "photo": 1})
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
    if not payload.body.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    doc = {"conversation_id": cid, "sender_id": user["id"], "body": payload.body.strip()[:2000],
           "read": False, "created_at": iso(now_utc())}
    res = await db.messages.insert_one(doc)
    await db.conversations.update_one({"_id": conv["_id"]},
                                      {"$set": {"last_message": doc["body"][:80], "updated_at": iso(now_utc())}})
    for m in conv["members"]:
        if m != user["id"]:
            await notify(m, "New message", f"{user['full_name']}: {doc['body'][:60]}", "message", "/messages", email=False)
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
    docs = await db.notifications.find({"user_id": user["id"]}).sort([("created_at", -1)]).to_list(100)
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
             "conversation_id": {"$in": [str(c["_id"]) for c in await db.conversations.find({"members": user["id"]}).to_list(100)]}}),
        "unread_notifications": await db.notifications.count_documents({"user_id": user["id"], "read": False}),
        "orders": await db.orders.count_documents({"user_id": user["id"]}),
        "upcoming_events": [clean(e) for e in await db.events.find(
            {"_id": {"$in": [ObjectId(p["event_id"]) for p in await db.event_participants.find({"user_id": user["id"]}).to_list(50)]}}
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
                                   {"referrer_id": 1}).to_list(5000)
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
                                           "notified_at": {"$in": [None, ""]}}).to_list(1000)
    if not pending:
        return 0
    slug = city_slug(city)
    country = country_for_city(city) or {}
    live = await db.events.count_documents({"city": city, "status": "published"})
    for w in pending:
        ok = await send_email(w["email"], f"Buddilio is now live in {city}", wrap(
            f"{city} is open",
            f"<p>You asked us to tell you the moment Buddilio opened in {city} — it just did.</p>"
            f"<p>There {'is' if live == 1 else 'are'} <b>{live} experience{'' if live == 1 else 's'}</b> "
            f"on the calendar right now, priced in {country.get('currency', BASE_CURRENCY)}, "
            "with verified members going to each one.</p>"
            "<p>Join free, tell us what you enjoy, and book the first night that looks like you.</p>",
            f"See what's on in {city}", f"{FRONTEND_URL}/city/{slug}"))
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


@api.post("/cron/city-openings")
async def cron_city_openings(_: None = Depends(cron_guard)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    asyncio.create_task(open_city_waitlists())
    return {"ok": True, "queued": "city-openings"}


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


@api.get("/cities/{slug}")
async def city_page(slug: str):
    city, country = find_city(slug)
    stamp = iso(now_utc())
    upcoming = await db.events.find({"city": city, "status": "published", "starts_at": {"$gte": stamp}}) \
        .sort([("starts_at", 1)]).limit(6).to_list(6)
    published = await db.events.find({"city": city, "status": "published"},
                                     {"_id": 1, "cover_image": 1, "category": 1, "starts_at": 1}).to_list(300)
    ids = [str(e["_id"]) for e in published]
    quotes = []
    for r in await db.reviews.find({"event_id": {"$in": ids}, "status": {"$ne": "hidden"},
                                    "comment": {"$nin": ["", None]}}) \
            .sort([("rating", -1), ("created_at", -1)]).limit(2).to_list(2):
        try:
            u = await db.users.find_one({"_id": ObjectId(r["user_id"])}, {"full_name": 1})
        except Exception:
            u = None
        quotes.append({"rating": r["rating"], "comment": r["comment"],
                       "user_name": short_name((u or {}).get("full_name", ""))})
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
        "guide": guide_for(city),
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
    extra = await db.cities.find({}).to_list(300)
    cats = await db.event_categories.find({}).to_list(100)
    ints = await db.interests.find({}).to_list(200)
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
            "currencies": [{"code": k, **v} for k, v in conf.items()],
            "settings": clean(await db.settings.find_one({}) or {"_id": ObjectId(), "platform_name": "Buddilio"})}


@api.get("/cms/{slug}")
async def cms_page(slug: str):
    doc = await db.cms_pages.find_one({"slug": slug})
    if not doc:
        raise HTTPException(status_code=404, detail="Page not found")
    return clean(doc)


@api.get("/cms")
async def cms_pages():
    return {"items": [clean(d) for d in await db.cms_pages.find({}).to_list(50)]}


# ---------------- admin ----------------
@api.get("/admin/stats")
async def admin_stats(days: int = 30, user: dict = Depends(admin_only)):
    since = iso(now_utc() - timedelta(days=days))
    paid = await db.orders.find({"payment_status": "paid", "created_at": {"$gte": since}}).to_list(2000)
    def rev(kind):
        return round(sum(o["total"] for o in paid if o["kind"] == kind), 2)
    users_total = await db.users.count_documents({"role": "user"})
    series = {}
    for o in paid:
        series[o["created_at"][:10]] = round(series.get(o["created_at"][:10], 0) + o["total"], 2)
    reg_series = {}
    for u in await db.users.find({"created_at": {"$gte": since}}, {"created_at": 1}).to_list(2000):
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
        "gross_sales": round(sum(o["total"] for o in paid), 2),
        "membership_revenue": rev("membership"), "event_revenue": rev("event"), "pass_revenue": rev("product"),
        "refunds": await db.orders.count_documents({"refund_status": {"$in": ["requested", "refunded"]}}),
        "pending_events": await db.events.count_documents({"status": "submitted"}),
        "open_reports": await db.reports.count_documents({"status": "open"}),
        "flagged_reviews": await db.reviews.count_documents({"flag_count": {"$gt": 0}, "status": {"$ne": "hidden"}}),
        "revenue_series": [{"date": k, "amount": v} for k, v in sorted(series.items())],
        "registration_series": [{"date": k, "count": v} for k, v in sorted(reg_series.items())],
    }


@api.get("/admin/users")
async def admin_users(q: str = "", role: str = "", status: str = "",
                      page: int = 1, limit: int = 20, user: dict = Depends(admin_only)):
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
        c = clean(d)
        c["membership"] = await membership_active(c["id"])
        items.append(c)
    return {"items": items, "total": total, "page": page}


@api.patch("/admin/users/{uid}")
async def admin_update_user(uid: str, body: dict, user: dict = Depends(admin_only)):
    allowed = {k: v for k, v in body.items()
               if k in ("status", "verified", "role", "full_name", "city", "email_verified")}
    if not allowed:
        raise HTTPException(status_code=400, detail="Nothing to update")
    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": allowed})
    await audit(user, "user.update", "user", uid, allowed)
    return clean(await db.users.find_one({"_id": ObjectId(uid)}))


@api.get("/admin/events")
async def admin_events(status: str = "", user: dict = Depends(admin_only)):
    flt = {"status": status} if status else {}
    docs = await db.events.find(flt).sort([("created_at", -1)]).to_list(300)
    return {"items": [clean(d) for d in docs]}


@api.post("/admin/events/{eid}/moderate")
async def moderate_event(eid: str, body: dict, user: dict = Depends(admin_only)):
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
    if ev.get("partner_id"):
        await notify(ev["partner_id"], f"Event {new_status}",
                     f"{ev['title']} was {new_status} by the Buddilio team.", "event", "/partner")
    if new_status == "published":
        asyncio.create_task(notify_city_waitlist(ev["city"]))
    return {"status": new_status}


@api.get("/admin/orders")
async def admin_orders(status: str = "", user: dict = Depends(admin_only)):
    flt = {"payment_status": status} if status else {}
    return {"items": [clean(d) for d in await db.orders.find(flt).sort([("created_at", -1)]).to_list(300)]}


@api.post("/admin/orders/{oid}/refund")
async def refund_order(oid: str, user: dict = Depends(admin_only)):
    order = await db.orders.find_one({"_id": ObjectId(oid)})
    if not order or order["payment_status"] != "paid":
        raise HTTPException(status_code=400, detail="Only paid orders can be refunded.")
    gateway_ref = ""
    client_rp = razorpay_client()
    if client_rp and order.get("gateway") == "razorpay" and order.get("transaction_id"):
        try:
            rf = await asyncio.to_thread(client_rp.payment.refund, order["transaction_id"],
                                         {"amount": int(round(order["total"] * 100)), "speed": "normal"})
            gateway_ref = rf.get("id", "")
        except Exception as e:
            logger.error(f"Razorpay refund failed: {e}")
            raise HTTPException(status_code=502, detail="The gateway rejected this refund. Please retry from the Razorpay dashboard.")
    await db.orders.update_one({"_id": order["_id"]},
                               {"$set": {"refund_status": "refunded", "order_status": "refunded",
                                         "refund_id": gateway_ref, "refunded_at": iso(now_utc())}})
    if order["kind"] == "membership":
        await db.user_memberships.update_many({"order_id": oid}, {"$set": {"status": "cancelled"}})
    if order["kind"] == "event":
        part = await db.event_participants.find_one({"order_id": oid})
        if part:
            await db.event_participants.delete_one({"_id": part["_id"]})
            count = await db.event_participants.count_documents({"event_id": order["ref_id"], "status": "confirmed"})
            await db.events.update_one({"_id": ObjectId(order["ref_id"])}, {"$set": {"participant_count": count}})
    await audit(user, "order.refund", "order", oid, {"amount": order["total"], "refund_id": gateway_ref})
    await notify(order["user_id"], "Refund processed",
                 f"{fmt_money(order.get('charge_total', order['total']), order.get('currency'))} for {order['item_name']} has been refunded. "
                 "It reaches your original payment method in 5-7 working days.", "refund", "/orders")
    return {"refund_status": "refunded", "refund_id": gateway_ref}


@api.get("/admin/reports")
async def admin_reports(status: str = "", user: dict = Depends(admin_only)):
    flt = {"status": status} if status else {}
    docs = await db.reports.find(flt).sort([("created_at", -1)]).to_list(300)
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
async def resolve_report(rid: str, body: dict, user: dict = Depends(admin_only)):
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
async def audit_logs(user: dict = Depends(admin_only)):
    return {"items": [clean(d) for d in await db.audit_logs.find({}).sort([("created_at", -1)]).to_list(200)]}


def crud_routes(path: str, coll: str, model):
    @api.post(f"/admin/{path}", name=f"create_{path}")
    async def create(payload: model, user: dict = Depends(admin_only)):  # type: ignore
        doc = payload.model_dump()
        if "code" in doc:
            doc["code"] = doc["code"].upper()
        doc["created_at"] = iso(now_utc())
        res = await db[coll].insert_one(doc)
        await audit(user, f"{path}.create", path, str(res.inserted_id), {})
        return clean(await db[coll].find_one({"_id": res.inserted_id}))

    @api.get(f"/admin/{path}", name=f"list_{path}")
    async def listing(user: dict = Depends(admin_only)):
        return {"items": [clean(d) for d in await db[coll].find({}).to_list(200)]}

    @api.put(f"/admin/{path}/{{item_id}}", name=f"update_{path}")
    async def update(item_id: str, payload: model, user: dict = Depends(admin_only)):  # type: ignore
        await db[coll].update_one({"_id": ObjectId(item_id)}, {"$set": payload.model_dump()})
        await audit(user, f"{path}.update", path, item_id, {})
        return clean(await db[coll].find_one({"_id": ObjectId(item_id)}))

    @api.delete(f"/admin/{path}/{{item_id}}", name=f"delete_{path}")
    async def delete(item_id: str, user: dict = Depends(admin_only)):
        await db[coll].delete_one({"_id": ObjectId(item_id)})
        await audit(user, f"{path}.delete", path, item_id, {})
        return {"ok": True}


crud_routes("plans", "membership_plans", PlanIn)
crud_routes("products", "products", ProductIn)
crud_routes("coupons", "coupons", CouponIn)


@api.put("/admin/cms/{slug}")
async def update_cms(slug: str, body: dict, user: dict = Depends(admin_only)):
    await db.cms_pages.update_one({"slug": slug},
                                  {"$set": {"title": body.get("title", slug), "content": body.get("content", ""),
                                            "seo_title": body.get("seo_title", ""),
                                            "seo_description": body.get("seo_description", ""),
                                            "updated_at": iso(now_utc())}}, upsert=True)
    await audit(user, "cms.update", "cms_page", slug, {})
    return clean(await db.cms_pages.find_one({"slug": slug}))


@api.get("/admin/settings")
async def get_settings(user: dict = Depends(admin_only)):
    return clean(await db.settings.find_one({}))


@api.put("/admin/settings")
async def update_settings(body: dict, user: dict = Depends(admin_only)):
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
    revs = await db.reviews.find({"event_id": event_id, **VISIBLE_REVIEW}, {"rating": 1}).to_list(1000)
    avg = round(sum(r["rating"] for r in revs) / len(revs), 2) if revs else 0
    await db.events.update_one({"_id": ObjectId(event_id)},
                               {"$set": {"rating": avg, "rating_count": len(revs)}})
    if partner_id:
        pr = await db.reviews.find({"partner_id": partner_id, **VISIBLE_REVIEW}, {"rating": 1}).to_list(5000)
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
    docs = await db.reviews.find(flt).sort([("created_at", -1)]).to_list(100)
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
    parts = await db.event_participants.find({"user_id": user["id"], "status": "confirmed"}).to_list(200)
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
    docs = await db.reviews.find({"partner_id": user["id"]}).sort([("created_at", -1)]).to_list(300)
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
async def admin_reviews(status: str = "", user: dict = Depends(admin_only)):
    if status == "flagged":
        flt: dict[str, Any] = {"flag_count": {"$gt": 0}, "status": {"$ne": "hidden"}}
    elif status:
        flt = {"status": status}
    else:
        flt = {}
    docs = await db.reviews.find(flt).sort([("flag_count", -1), ("created_at", -1)]).to_list(300)
    out = []
    for d in docs:
        r = await review_author(clean(d))
        try:
            ev = await db.events.find_one({"_id": ObjectId(r["event_id"])}, {"title": 1, "partner_name": 1})
        except Exception:
            ev = None
        r["event_title"] = ev["title"] if ev else "Experience"
        r["partner_name"] = (ev or {}).get("partner_name", "")
        r["reports"] = [{"reason": rp["reason"], "by": rp["reporter_email"], "at": rp["created_at"]}
                        for rp in await db.reports.find({"target_type": "review", "target_id": r["id"]}).to_list(20)]
        out.append(r)
    return {"items": out,
            "flagged": await db.reviews.count_documents({"flag_count": {"$gt": 0}, "status": {"$ne": "hidden"}}),
            "hidden": await db.reviews.count_documents({"status": "hidden"}),
            "total": await db.reviews.count_documents({})}


@api.post("/admin/reviews/{rid}/moderate")
async def moderate_review(rid: str, body: dict, user: dict = Depends(admin_only)):
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
                                           {"starts_at": {"$lt": cutoff}}]}).to_list(500)
    created = 0
    for ev in events:
        eid = str(ev["_id"])
        if ev.get("status") == "published":
            await db.events.update_one({"_id": ev["_id"]}, {"$set": {"status": "completed"}})
        if not ev.get("partner_id") or await db.payouts.find_one({"event_id": eid}):
            continue
        orders = await db.orders.find({"kind": "event", "ref_id": eid, "payment_status": "paid",
                                       "refund_status": "none"}).to_list(1000)
        gross = round(sum(o["subtotal"] - o["discount"] for o in orders), 2)
        fee = round(gross * PLATFORM_FEE / 100, 2)
        await db.payouts.insert_one({
            "partner_id": ev["partner_id"], "event_id": eid, "event_title": ev["title"],
            "orders": len(orders), "gross": gross, "fee_percent": PLATFORM_FEE, "fee": fee,
            "net": round(gross - fee, 2), "currency": "INR", "status": "pending",
            "created_at": iso(now_utc())})
        created += 1
        await notify(ev["partner_id"], "Payout ready",
                     f"Your payout for {ev['title']} (₹{round(gross - fee):,}) is queued for settlement.",
                     "order", "/partner")
    return created


@api.get("/partner/payouts")
async def partner_payouts(user: dict = Depends(partner_only)):
    docs = await db.payouts.find({"partner_id": user["id"]}).sort([("created_at", -1)]).to_list(300)
    items = [clean(d) for d in docs]
    return {"items": items,
            "pending_total": round(sum(i["net"] for i in items if i["status"] == "pending"), 2),
            "paid_total": round(sum(i["net"] for i in items if i["status"] == "paid"), 2)}


@api.get("/admin/payouts")
async def admin_payouts(status: str = "", user: dict = Depends(admin_only)):
    flt = {"status": status} if status else {}
    docs = await db.payouts.find(flt).sort([("created_at", -1)]).to_list(500)
    out = []
    for d in docs:
        p = clean(d)
        partner = await db.users.find_one({"_id": ObjectId(p["partner_id"])}, {"full_name": 1, "org_name": 1, "email": 1})
        p["partner"] = clean(partner) if partner else None
        out.append(p)
    return {"items": out}


@api.post("/admin/payouts/{pid}/pay")
async def pay_payout(pid: str, body: dict, user: dict = Depends(admin_only)):
    payout = await db.payouts.find_one({"_id": ObjectId(pid)})
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout["status"] == "paid":
        raise HTTPException(status_code=400, detail="This payout is already settled.")
    ref = body.get("reference") or "UTR" + uuid.uuid4().hex[:10].upper()
    await db.payouts.update_one({"_id": payout["_id"]},
                                {"$set": {"status": "paid", "reference": ref, "paid_at": iso(now_utc())}})
    await audit(user, "payout.pay", "payout", pid, {"net": payout["net"], "reference": ref})
    await notify(payout["partner_id"], "Payout settled",
                 f"{fmt_money(payout['net'])} for {payout['event_title']} has been transferred. Reference {ref}.",
                 "order", "/partner")
    return {"status": "paid", "reference": ref}


@api.post("/admin/payouts/generate")
async def run_payout_generation(user: dict = Depends(admin_only)):
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
    convs = await db.conversations.find({"members": uid}, {"members": 1}).to_list(200)
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
            events = await db.events.find({"status": "published", "starts_at": {"$gte": iso(now_utc()), "$lte": window_end}}).to_list(200)
            for ev in events:
                eid = str(ev["_id"])
                parts = await db.event_participants.find({"event_id": eid, "status": "confirmed"}).to_list(500)
                starts = datetime.fromisoformat(ev["starts_at"])
                for p in parts:
                    if p.get("reminded"):
                        continue
                    await db.event_participants.update_one({"_id": p["_id"]}, {"$set": {"reminded": True}})
                    await notify(p["user_id"], "Event reminder",
                                 f"{ev['title']} starts {starts.strftime('%a %d %b at %I:%M %p')} — {ev.get('venue','')}, {ev['city']}.",
                                 "reminder", f"/events/{eid}", email=False)
                    u = await db.users.find_one({"_id": ObjectId(p["user_id"])},
                                                {"email": 1, "full_name": 1, "notification_prefs": 1})
                    if u and (u.get("notification_prefs") or {}).get("email", True):
                        await send_email(u["email"], f"Tomorrow: {ev['title']}", wrap(
                            "See you tomorrow",
                            f"<p>Hi {u['full_name'].split(' ')[0]},</p>"
                            f"<p><b>{ev['title']}</b> starts <b>{starts.strftime('%a %d %b, %I:%M %p')}</b>.</p>"
                            f"<p><b>Venue:</b> {ev.get('venue','')}, {ev['city']}<br/>"
                            f"<b>Host:</b> {ev.get('partner_name','Buddilio')}</p>"
                            "<p>Carry a government photo ID. Meet other members in the public venue only.</p>",
                            "View event", f"{FRONTEND_URL}/events/{eid}"))
        except Exception as e:
            logger.error(f"reminder loop error: {e}")
        await asyncio.sleep(3600)


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
    await db.users.create_index("email", unique=True)
    await db.users.create_index([("city", 1), ("role", 1)])
    await db.events.create_index([("status", 1), ("starts_at", 1)])
    await db.events.create_index([("city", 1), ("category", 1)])
    await db.event_participants.create_index([("event_id", 1), ("user_id", 1)])
    await db.messages.create_index([("conversation_id", 1), ("created_at", 1)])
    await db.notifications.create_index([("user_id", 1), ("read", 1)])
    await db.orders.create_index([("user_id", 1), ("created_at", -1)])
    await db.payouts.create_index("event_id", unique=True)
    await db.reviews.create_index([("event_id", 1), ("user_id", 1)], unique=True)
    await db.push_subscriptions.create_index("endpoint", unique=True)
    await db.city_waitlist.create_index([("city", 1), ("email", 1)], unique=True)
    await db.prizes.create_index("month", unique=True)
    await db.push_subscriptions.create_index("user_id")
    await db.referrals.create_index("invitee_id", unique=True)
    await db.referrals.create_index("referrer_id")
    await db.credits.create_index([("user_id", 1), ("created_at", -1)])
    await db.users.create_index("referral_code", sparse=True)
    await db.login_attempts.create_index("identifier")
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    admin_email = os.environ["ADMIN_EMAIL"]
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "full_name": "Buddilio Admin", "email": admin_email,
            "password_hash": hash_password(os.environ["ADMIN_PASSWORD"]), "role": "admin",
            "status": "active", "city": "Delhi NCR", "age": 35, "photo": "", "bio": "",
            "interests": [], "event_categories": [], "blocked": [], "connections": [],
            "saved_events": [], "verified": True, "created_at": iso(now_utc())})
    elif not verify_password(os.environ["ADMIN_PASSWORD"], existing.get("password_hash", "")):
        await db.users.update_one({"_id": existing["_id"]},
                                  {"$set": {"password_hash": hash_password(os.environ["ADMIN_PASSWORD"])}})
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
