"""Vendor agreement, commercial schedule, pricing and settlement endpoints.

server.py calls register(deps) once at import time; every shared helper (db, audit, permissions,
email) is injected so this module stays free of circular imports.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from bson import ObjectId
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

import agreements as agr

D: dict = {}          # injected dependencies
OTP_MINUTES = 10


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt) -> str:
    return dt.isoformat()


def oid(value: str, label: str = "record") -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(status_code=400, detail=f"That {label} id is not valid.")


# ---------------- payloads ----------------
class VendorIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    legal_name: str
    trade_name: str = ""
    vendor_kind: Literal["organiser", "travel_provider", "companion"] = "organiser"
    contact_person: str = ""
    email: str
    phone: str = ""
    registered_address: str = ""
    operating_address: str = ""
    pan: str = ""
    gstin: str = ""
    registration_details: str = ""
    bank_account_name: str = ""
    bank_account_number: str = ""
    bank_ifsc: str = ""
    service_category: str = ""
    service_description: str = ""
    city: str = ""
    country: str = "India"
    website: str = ""
    licenses: str = ""
    user_id: str = ""
    agreement_end_date: str = ""
    auto_renew: bool = True
    renewal_notice_days: int = 30


class VendorStatusIn(BaseModel):
    status: Literal["draft", "submitted", "under_review", "documents_required", "approved",
                    "rejected", "suspended", "terminated"]
    reason: str = ""


class DocIn(BaseModel):
    doc_type: str
    path: str
    expires_on: str = ""


class DocReviewIn(BaseModel):
    status: Literal["pending", "approved", "rejected", "expired"]
    note: str = ""


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    service_id: str = ""
    service_name: str = ""
    currency: str = "INR"
    vendor_net_rate: float = Field(ge=0)
    pricing_floor: float = Field(default=0, ge=0)
    commission_type: Literal["percentage", "fixed", "hybrid"] = "percentage"
    commission_value: float = Field(default=0, ge=0)
    commission_fixed: float = Field(default=0, ge=0)
    platform_fee_percent: float = Field(default=10, ge=0, le=100)
    platform_fee_fixed: float = Field(default=0, ge=0)
    tax_percent: float = Field(default=0, ge=0, le=100)
    dynamic_pricing_enabled: bool = False
    promotion_discount: float = Field(default=0, ge=0)
    discount_funding: Literal["buddilio", "vendor", "shared"] = "buddilio"
    settlement_cycle: Literal["T+1", "T+3", "T+7", "T+15", "custom"] = "T+7"
    settlement_cycle_custom: str = ""
    cancellation_policy: str = ""
    refund_responsibility: Literal["vendor", "buddilio", "shared"] = "vendor"
    payment_processing: str = "Borne by Buddilio"
    rate_policy: Literal["none", "notify", "parity_law", "custom"] = "none"
    rate_policy_note: str = ""
    effective_from: str = ""
    effective_until: str = ""
    change_reason: str = ""


class PreviewIn(BaseModel):
    schedule: dict
    quantity: int = 1
    dynamic_adjustment: float = 0
    discount: float = 0


class OtpRequestIn(BaseModel):
    channel: Literal["email"] = "email"


class AcceptIn(BaseModel):
    otp: str
    accepted_by: str
    read_agreement: bool
    authorised: bool
    accept_commercials: bool
    consent_electronic: bool


class TerminateIn(BaseModel):
    reason: Literal["vendor_request", "buddilio_decision", "compliance", "fraud", "safety",
                    "repeated_cancellation", "poor_service", "non_payment", "breach",
                    "business_closure", "other"]
    note: str = ""


# ---------------- helpers ----------------
async def vendor_or_404(vid: str) -> dict:
    doc = await D["db"].vendor_profiles.find_one({"_id": oid(vid, "vendor")})
    if not doc:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    return doc


async def my_vendor(user: dict) -> dict:
    doc = await D["db"].vendor_profiles.find_one({"user_id": user["id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="No vendor profile yet. Complete vendor registration first.")
    return doc


async def active_schedule(vendor_id: str, service_id: str = "") -> Optional[dict]:
    """The schedule in force right now — accepted and already effective (spec §43).

    A schedule accepted with a future effective_from waits as `scheduled`; the previous version keeps
    applying until its start time passes, then it is promoted here.
    """
    db = D["db"]
    now = iso(now_utc())
    due = await db.commercial_schedules.find(
        {"vendor_id": vendor_id, "status": "scheduled", "effective_from": {"$lte": now}}
    ).sort("version", 1).to_list(20)
    for s in due:
        await db.commercial_schedules.update_one({"_id": s["_id"]}, {"$set": {"status": "active"}})
        await db.commercial_schedules.update_many(
            {"vendor_id": vendor_id, "_id": {"$ne": s["_id"]}, "status": "active"},
            {"$set": {"status": "superseded", "effective_until": s["effective_from"]}})

    q = {"vendor_id": vendor_id, "status": "active", "effective_from": {"$lte": now}}
    if service_id:
        docs = await db.commercial_schedules.find({**q, "service_id": service_id}).sort("version", -1).to_list(1)
        if docs:
            return D["clean"](docs[0])
    docs = await db.commercial_schedules.find(q).sort("version", -1).to_list(1)
    return D["clean"](docs[0]) if docs else None


async def latest_agreement(vendor_id: str) -> Optional[dict]:
    docs = await D["db"].vendor_agreements.find({"vendor_id": vendor_id}).sort("created_at", -1).to_list(1)
    return D["clean"](docs[0]) if docs else None


async def entity_settings() -> dict:
    s = await D["db"].settings.find_one({}, {"vendor_entity": 1}) or {}
    return {**agr.ENTITY, **(s.get("vendor_entity") or {})}


def schedule_summary(s: dict) -> str:
    return (f"Net rate {agr.money(s.get('vendor_net_rate'), s.get('currency', 'INR'))} · "
            f"commission {agr.commission_label(s)} · platform fee {agr.platform_fee_label(s)} · "
            f"settlement {s.get('settlement_cycle', 'T+7')}")


def diff_schedules(old: dict, new: dict) -> list[dict]:
    out = []
    for f in agr.MATERIAL_FIELDS + ["platform_fee_percent", "dynamic_pricing_enabled", "rate_policy"]:
        a, b = old.get(f), new.get(f)
        if a != b and f not in [d["field"] for d in out]:
            out.append({"field": f, "label": f.replace("_", " "), "from": a, "to": b})
    return out


async def docs_complete(vendor_id: str) -> bool:
    docs = await D["db"].vendor_documents.find({"vendor_id": vendor_id}).to_list(100)
    approved = {d["doc_type"] for d in docs if d.get("status") == "approved"}
    return all(k in approved for k in agr.REQUIRED_DOCS)


async def vendor_for_order(order: dict) -> str:
    """Which vendor profile earns from this order, if any."""
    db = D["db"]
    if order.get("vendor_profile_id"):
        return order["vendor_profile_id"]
    owner = ""
    kind, ref = order.get("kind"), order.get("ref_id", "")
    try:
        if kind == "event" and ref:
            ev = await db.events.find_one({"_id": ObjectId(ref)}, {"partner_id": 1})
            owner = (ev or {}).get("partner_id", "")
        elif kind == "travel" and ref:
            b = await db.travel_bookings.find_one({"_id": ObjectId(ref)}, {"provider_user_id": 1, "provider_id": 1})
            owner = (b or {}).get("provider_user_id") or (b or {}).get("provider_id") or ""
        elif kind == "companion" and ref:
            b = await db.hangout_bookings.find_one({"_id": ObjectId(ref)}, {"companion_id": 1})
            owner = (b or {}).get("companion_id", "")
    except Exception:
        owner = ""
    if not owner:
        return ""
    v = await db.vendor_profiles.find_one({"user_id": owner}, {"_id": 1})
    return str(v["_id"]) if v else ""


async def snapshot_booking(order: dict) -> Optional[dict]:
    """Freeze the commercial terms onto a booking so history is never recalculated."""
    db = D["db"]
    vendor_id = await vendor_for_order(order)
    if not vendor_id:
        return None
    existing = await db.booking_commercial_snapshots.find_one({"booking_id": str(order["_id"])})
    if existing:
        return D["clean"](existing)
    sched = await active_schedule(vendor_id, order.get("ref_id", ""))
    if not sched:
        return None
    ag = await latest_agreement(vendor_id)
    priced = agr.calculate_price(sched, quantity=int(order.get("quantity") or 1),
                                discount=float(order.get("discount") or 0))
    snap = {"booking_id": str(order["_id"]), "order_no": order.get("order_no", ""),
            "vendor_id": vendor_id, "agreement_id": (ag or {}).get("id", ""),
            "agreement_version": (ag or {}).get("version", ""),
            "commercial_schedule_id": sched["id"], "commercial_schedule_version": sched["version"],
            **{k: priced[k] for k in ("currency", "vendor_net_rate", "pricing_floor", "commission",
                                      "platform_fee", "discount", "tax", "customer_price",
                                      "vendor_settlement", "buddilio_earning")},
            "cancellation_policy": sched.get("cancellation_policy", ""),
            "settlement_cycle": sched.get("settlement_cycle", "T+7"),
            "created_at": iso(now_utc())}
    await db.booking_commercial_snapshots.insert_one(snap)
    cycle = {"T+1": 1, "T+3": 3, "T+7": 7, "T+15": 15}.get(snap["settlement_cycle"], 7)
    await db.vendor_settlements.insert_one({
        "vendor_id": vendor_id, "booking_id": snap["booking_id"], "order_no": snap["order_no"],
        "gross": snap["customer_price"], "commission": snap["commission"], "platform_fee": snap["platform_fee"],
        "refunds": 0.0, "adjustments": 0.0, "net": snap["vendor_settlement"], "currency": snap["currency"],
        "status": "pending", "due_on": iso(now_utc() + timedelta(days=cycle)), "created_at": iso(now_utc())})
    return snap


def register(deps: dict):
    """Wire the routes onto the shared API router."""
    D.update(deps)
    api = deps["api"]
    db = deps["db"]
    clean = deps["clean"]
    audit = deps["audit"]
    require_perm = deps["require_perm"]
    get_current_user = deps["get_current_user"]
    notify = deps["notify"]
    send_tpl = deps["send_tpl"]
    first_name = deps["first_name"]
    site_url = deps["site_url"]

    manage = require_perm("agreements:manage")
    view = require_perm("vendors:view")

    # ---------------- meta ----------------
    @api.get("/vendor-agreements/meta")
    async def meta():
        s = await db.settings.find_one({}, {"platform_commission_percent": 1, "platform_fee_percent": 1}) or {}
        return {"vendor_kinds": agr.VENDOR_KINDS, "vendor_statuses": agr.VENDOR_STATUSES,
                "agreement_statuses": agr.AGREEMENT_STATUSES, "settlement_cycles": agr.SETTLEMENT_CYCLES,
                "commission_types": agr.COMMISSION_TYPES, "rate_policies": agr.RATE_POLICIES,
                "refund_responsibility": agr.REFUND_RESPONSIBILITY, "discount_funding": agr.DISCOUNT_FUNDING,
                "doc_types": agr.DOC_TYPES, "termination_reasons": agr.TERMINATION_REASONS,
                "entity": await entity_settings(),
                "default_commission_percent": float(s.get("platform_commission_percent") or 25),
                "default_platform_fee_percent": float(s.get("platform_fee_percent") or 10)}

    # ---------------- vendor self-service ----------------
    @api.post("/vendor/profile")
    async def upsert_profile(payload: VendorIn, user: dict = Depends(get_current_user)):
        existing = await db.vendor_profiles.find_one({"user_id": user["id"]})
        body = payload.model_dump()
        body.update({"user_id": user["id"], "updated_at": iso(now_utc())})
        if existing:
            if existing.get("status") in ("approved", "suspended", "terminated"):
                # Approved vendors can refresh contact details but not silently rewrite their legal identity.
                for locked in ("legal_name", "pan", "gstin"):
                    body.pop(locked, None)
            await db.vendor_profiles.update_one({"_id": existing["_id"]}, {"$set": body})
            doc = await db.vendor_profiles.find_one({"_id": existing["_id"]})
        else:
            body.update({"status": "draft", "created_at": iso(now_utc())})
            res = await db.vendor_profiles.insert_one(body)
            doc = await db.vendor_profiles.find_one({"_id": res.inserted_id})
            await audit(user, "VENDOR_CREATED", "vendor_profile", str(res.inserted_id),
                        {"legal_name": payload.legal_name})
        return {"vendor": clean(doc)}

    @api.post("/vendor/profile/submit")
    async def submit_profile(user: dict = Depends(get_current_user)):
        v = await my_vendor(user)
        missing = [f for f in ("legal_name", "contact_person", "pan", "registered_address", "service_category")
                   if not (v.get(f) or "").strip()]
        if missing:
            raise HTTPException(status_code=400,
                                detail="Please complete: " + ", ".join(m.replace('_', ' ') for m in missing))
        await db.vendor_profiles.update_one({"_id": v["_id"]},
                                           {"$set": {"status": "submitted", "submitted_at": iso(now_utc())}})
        await audit(user, "VENDOR_SUBMITTED", "vendor_profile", str(v["_id"]))
        return {"ok": True, "status": "submitted"}

    @api.get("/vendor/profile")
    async def get_profile(user: dict = Depends(get_current_user)):
        doc = await db.vendor_profiles.find_one({"user_id": user["id"]})
        if not doc:
            return {"vendor": None, "documents": [], "required": agr.REQUIRED_DOCS}
        docs = await db.vendor_documents.find({"vendor_id": str(doc["_id"])}).to_list(100)
        return {"vendor": clean(doc), "documents": [clean(d) for d in docs],
                "required": agr.REQUIRED_DOCS, "documents_complete": await docs_complete(str(doc["_id"]))}

    @api.post("/vendor/documents")
    async def add_document(payload: DocIn, user: dict = Depends(get_current_user)):
        v = await my_vendor(user)
        if payload.doc_type not in [d["key"] for d in agr.DOC_TYPES]:
            raise HTTPException(status_code=400, detail="Unknown document type.")
        body = {"vendor_id": str(v["_id"]), "doc_type": payload.doc_type, "path": payload.path,
                "expires_on": payload.expires_on, "status": "pending", "note": "",
                "uploaded_at": iso(now_utc())}
        await db.vendor_documents.update_one({"vendor_id": body["vendor_id"], "doc_type": payload.doc_type},
                                            {"$set": body}, upsert=True)
        await audit(user, "VENDOR_DOCUMENT_UPLOADED", "vendor_profile", str(v["_id"]),
                    {"doc_type": payload.doc_type})
        return {"ok": True}

    @api.get("/vendor/agreement")
    async def vendor_agreement(user: dict = Depends(get_current_user)):
        v = await my_vendor(user)
        ag = await latest_agreement(str(v["_id"]))
        sched = None
        if ag:
            sched = clean(await db.commercial_schedules.find_one({"_id": oid(ag["commercial_schedule_id"])})) \
                if ag.get("commercial_schedule_id") else None
        acc = None
        if ag:
            a = await db.agreement_acceptances.find_one({"agreement_id": ag["id"], "version": ag["version"]})
            acc = clean(a) if a else None
        return {"vendor": clean(v), "agreement": ag, "schedule": sched, "acceptance": acc,
                "entity": await entity_settings(),
                "sections": agr.agreement_sections(dict(clean(v), **(ag or {})), sched or {},
                                                   await entity_settings()) if ag and sched else [],
                "commercial_rows": agr.commercial_rows(sched) if sched else []}

    @api.get("/vendor/commercial-terms")
    async def vendor_terms(user: dict = Depends(get_current_user)):
        v = await my_vendor(user)
        sched = await active_schedule(str(v["_id"]))
        return {"schedule": sched, "rows": agr.commercial_rows(sched) if sched else []}

    @api.get("/vendor/agreement/history")
    async def vendor_history(user: dict = Depends(get_current_user)):
        v = await my_vendor(user)
        ags = await db.vendor_agreements.find({"vendor_id": str(v["_id"])}).sort("created_at", -1).to_list(50)
        scheds = await db.commercial_schedules.find({"vendor_id": str(v["_id"])}).sort("version", -1).to_list(50)
        accs = await db.agreement_acceptances.find({"vendor_id": str(v["_id"])}).sort("accepted_at", -1).to_list(50)
        return {"agreements": [clean(a) for a in ags], "schedules": [clean(s) for s in scheds],
                "acceptances": [clean(a) for a in accs]}

    @api.get("/vendor/settlements")
    async def vendor_settlements(user: dict = Depends(get_current_user)):
        v = await my_vendor(user)
        rows = await db.vendor_settlements.find({"vendor_id": str(v["_id"])}).sort("created_at", -1).to_list(500)
        out = [clean(r) for r in rows]
        return {"items": out,
                "totals": {"paid": round(sum(r["net"] for r in out if r["status"] == "paid"), 2),
                           "pending": round(sum(r["net"] for r in out if r["status"] != "paid"), 2)}}

    # ---------------- acceptance ----------------
    @api.post("/vendor/agreement/otp")
    async def request_otp(payload: OtpRequestIn, user: dict = Depends(get_current_user)):
        v = await my_vendor(user)
        ag = await latest_agreement(str(v["_id"]))
        if not ag or ag["status"] not in ("pending_vendor_acceptance", "amendment_pending"):
            raise HTTPException(status_code=400, detail="There is nothing awaiting your acceptance.")
        code = f"{secrets.randbelow(900000) + 100000}"
        ref = "OTP-" + uuid.uuid4().hex[:10].upper()
        await db.agreement_otps.update_one(
            {"agreement_id": ag["id"], "version": ag["version"]},
            {"$set": {"vendor_id": str(v["_id"]), "code_hash": hashlib.sha256(code.encode()).hexdigest(),
                      "reference": ref, "channel": payload.channel, "attempts": 0,
                      "expires_at": iso(now_utc() + timedelta(minutes=OTP_MINUTES)),
                      "created_at": iso(now_utc())}}, upsert=True)
        await send_tpl("vendor_agreement_otp", v.get("email") or user["email"],
                       {"first_name": first_name(v.get("contact_person") or user["full_name"]),
                        "otp": code, "agreement_number": ag["agreement_number"], "minutes": str(OTP_MINUTES)})
        await audit(user, "AGREEMENT_OTP_SENT", "vendor_agreement", ag["id"], {"reference": ref})
        return {"ok": True, "reference": ref, "sent_to": v.get("email") or user["email"],
                "expires_in_minutes": OTP_MINUTES}

    @api.post("/vendor/agreement/accept")
    async def accept_agreement(payload: AcceptIn, request: Request, user: dict = Depends(get_current_user)):
        if not all([payload.read_agreement, payload.authorised, payload.accept_commercials,
                    payload.consent_electronic]):
            raise HTTPException(status_code=400, detail="All four confirmations are required.")
        v = await my_vendor(user)
        ag = await latest_agreement(str(v["_id"]))
        if not ag or ag["status"] not in ("pending_vendor_acceptance", "amendment_pending"):
            raise HTTPException(status_code=400, detail="There is nothing awaiting your acceptance.")
        otp = await db.agreement_otps.find_one({"agreement_id": ag["id"], "version": ag["version"]})
        if not otp:
            raise HTTPException(status_code=400, detail="Request a verification code first.")
        if otp["expires_at"] < iso(now_utc()):
            raise HTTPException(status_code=400, detail="That code has expired. Please request a new one.")
        if int(otp.get("attempts", 0)) >= 5:
            raise HTTPException(status_code=429, detail="Too many attempts. Request a new code.")
        if hashlib.sha256(payload.otp.strip().encode()).hexdigest() != otp["code_hash"]:
            await db.agreement_otps.update_one({"_id": otp["_id"]}, {"$inc": {"attempts": 1}})
            raise HTTPException(status_code=400, detail="That code is not correct.")

        sched = clean(await db.commercial_schedules.find_one({"_id": oid(ag["commercial_schedule_id"])}))
        entity = await entity_settings()
        vendor_ctx = dict(clean(v), agreement_number=ag["agreement_number"], version=ag["version"])
        text = agr.agreement_text(vendor_ctx, sched, entity)
        digest = agr.document_hash(text)
        acceptance = {
            "agreement_id": ag["id"], "vendor_id": str(v["_id"]), "version": ag["version"],
            "commercial_schedule_id": sched["id"], "commercial_schedule_version": sched["version"],
            "vendor_name": v.get("legal_name", ""), "accepted_by": payload.accepted_by.strip(),
            "email": v.get("email") or user["email"], "phone": v.get("phone", ""),
            "acceptance_method": "otp_email", "otp_reference": otp["reference"], "signature_reference": "",
            "ip_address": (request.client.host if request.client else ""),
            "user_agent": request.headers.get("user-agent", "")[:400],
            "accepted_at": iso(now_utc()), "time_zone": "UTC", "document_hash": digest,
            "agreement_text": text, "status": "accepted", "locked": True,
            "confirmations": {"read_agreement": True, "authorised": True,
                              "accept_commercials": True, "consent_electronic": True},
        }
        res = await db.agreement_acceptances.insert_one(acceptance)
        pdf = agr.agreement_pdf({**ag, "status": "active"}, clean(v), sched, acceptance, entity)
        await db.agreement_documents.insert_one({"agreement_id": ag["id"], "version": ag["version"],
                                                "pdf": pdf, "document_hash": digest,
                                                "created_at": iso(now_utc())})
        await db.vendor_agreements.update_one(
            {"_id": oid(ag["id"])},
            {"$set": {"status": "active", "accepted_at": acceptance["accepted_at"],
                      "accepted_by": acceptance["accepted_by"], "acceptance_id": str(res.inserted_id),
                      "document_hash": digest, "agreement_text": text}})
        # A future-dated schedule waits its turn; the current one keeps applying until then.
        future = sched.get("effective_from", "") > iso(now_utc())
        await db.commercial_schedules.update_one(
            {"_id": oid(sched["id"])}, {"$set": {"status": "scheduled" if future else "active"}})
        if not future:
            await db.commercial_schedules.update_many(
                {"vendor_id": str(v["_id"]), "_id": {"$ne": oid(sched["id"])}, "status": "active"},
                {"$set": {"status": "superseded", "effective_until": acceptance["accepted_at"]}})
        await db.agreement_otps.delete_one({"_id": otp["_id"]})
        await audit(user, "AGREEMENT_ACCEPTED", "vendor_agreement", ag["id"],
                    {"version": ag["version"], "hash": digest, "method": "otp_email"})

        await send_tpl("vendor_agreement_accepted", acceptance["email"], {
            "first_name": first_name(acceptance["accepted_by"]), "agreement_number": ag["agreement_number"],
            "version": str(ag["version"]), "effective_date": str(ag.get("effective_date", ""))[:10],
            "commercial_summary": schedule_summary(sched),
            "dashboard_url": f"{site_url()}/vendor/agreement",
            "agreement_url": f"{site_url()}/vendor/agreement"})
        for admin in await db.users.find({"role": "admin"}, {"_id": 1}).to_list(20):
            await notify(str(admin["_id"]), "Vendor agreement accepted",
                         f"{v.get('legal_name')} accepted {ag['agreement_number']} v{ag['version']} "
                         f"({schedule_summary(sched)})", "vendor", "/admin")
        return {"ok": True, "agreement_number": ag["agreement_number"], "version": ag["version"],
                "accepted_at": acceptance["accepted_at"], "accepted_by": acceptance["accepted_by"],
                "method": "OTP (email)", "document_hash": digest}

    # ---------------- executed PDF ----------------
    @api.get("/vendor-agreements/{aid}/pdf")
    async def agreement_pdf_download(aid: str, user: dict = Depends(get_current_user)):
        ag = await db.vendor_agreements.find_one({"_id": oid(aid, "agreement")})
        if not ag:
            raise HTTPException(status_code=404, detail="Agreement not found.")
        v = await db.vendor_profiles.find_one({"_id": oid(ag["vendor_id"], "vendor")})
        allowed = user["role"] == "admin" or (v and v.get("user_id") == user["id"])
        if not allowed and "agreements:manage" not in deps["perms_of"](user):
            raise HTTPException(status_code=403, detail="That agreement isn't yours.")
        stored = await db.agreement_documents.find_one({"agreement_id": aid, "version": ag["version"]})
        if stored:
            pdf = stored["pdf"]
        else:
            sched = clean(await db.commercial_schedules.find_one({"_id": oid(ag["commercial_schedule_id"])}))
            pdf = agr.agreement_pdf(clean(ag), clean(v), sched, None, await entity_settings())
        name = f"{ag['agreement_number']}-v{ag['version']}.pdf"
        await audit(user, "AGREEMENT_VIEWED", "vendor_agreement", aid, {"format": "pdf"})
        return deps["Response"](content=bytes(pdf), media_type="application/pdf",
                                headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # ---------------- admin: vendors ----------------
    @api.get("/admin/vendor-profiles")
    async def admin_vendors(status: str = "", kind: str = "", user: dict = Depends(view)):
        q = {}
        if status:
            q["status"] = status
        if kind:
            q["vendor_kind"] = kind
        docs = await db.vendor_profiles.find(q).sort("created_at", -1).to_list(500)
        out = []
        for d in docs:
            row = clean(d)
            row["agreement"] = await latest_agreement(row["id"])
            row["schedule"] = await active_schedule(row["id"])
            row["documents_complete"] = await docs_complete(row["id"])
            out.append(row)
        return {"items": out}

    @api.post("/admin/vendor-profiles")
    async def admin_create_vendor(payload: VendorIn, user: dict = Depends(manage)):
        body = payload.model_dump()
        body.update({"status": "under_review", "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
                     "created_by": user["id"]})
        res = await db.vendor_profiles.insert_one(body)
        await audit(user, "VENDOR_CREATED", "vendor_profile", str(res.inserted_id),
                    {"legal_name": payload.legal_name})
        return {"vendor": clean(await db.vendor_profiles.find_one({"_id": res.inserted_id}))}

    @api.put("/admin/vendor-profiles/{vid}")
    async def admin_update_vendor(vid: str, payload: VendorIn, user: dict = Depends(manage)):
        v = await vendor_or_404(vid)
        await db.vendor_profiles.update_one({"_id": v["_id"]},
                                           {"$set": {**payload.model_dump(), "updated_at": iso(now_utc())}})
        await audit(user, "VENDOR_UPDATED", "vendor_profile", vid)
        return {"vendor": clean(await db.vendor_profiles.find_one({"_id": v["_id"]}))}

    @api.patch("/admin/vendor-profiles/{vid}/status")
    async def admin_vendor_status(vid: str, payload: VendorStatusIn, user: dict = Depends(manage)):
        v = await vendor_or_404(vid)
        if payload.status == "approved" and not await docs_complete(vid):
            raise HTTPException(status_code=400,
                                detail="Approve the mandatory documents (PAN, bank proof, address proof) first.")
        await db.vendor_profiles.update_one(
            {"_id": v["_id"]}, {"$set": {"status": payload.status, "status_reason": payload.reason,
                                         "status_changed_at": iso(now_utc())}})
        await audit(user, f"VENDOR_{payload.status.upper()}", "vendor_profile", vid,
                    {"from": v.get("status"), "to": payload.status, "reason": payload.reason})
        if v.get("user_id"):
            await notify(v["user_id"], f"Vendor account {payload.status.replace('_', ' ')}",
                         payload.reason or "Open your vendor portal for details.", "vendor", "/vendor/agreement")
        return {"ok": True, "status": payload.status}

    @api.get("/admin/vendor-profiles/{vid}/documents")
    async def admin_vendor_docs(vid: str, user: dict = Depends(view)):
        docs = await db.vendor_documents.find({"vendor_id": vid}).to_list(100)
        return {"items": [clean(d) for d in docs], "required": agr.REQUIRED_DOCS,
                "complete": await docs_complete(vid)}

    @api.patch("/admin/vendor-documents/{did}")
    async def review_document(did: str, payload: DocReviewIn, user: dict = Depends(manage)):
        doc = await db.vendor_documents.find_one({"_id": oid(did, "document")})
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found.")
        await db.vendor_documents.update_one({"_id": doc["_id"]},
                                            {"$set": {"status": payload.status, "note": payload.note,
                                                      "reviewed_at": iso(now_utc()), "reviewed_by": user["id"]}})
        await audit(user, "VENDOR_DOCUMENT_REVIEWED", "vendor_profile", doc["vendor_id"],
                    {"doc_type": doc["doc_type"], "status": payload.status})
        return {"ok": True}

    # ---------------- admin: commercial schedules + agreements ----------------
    async def next_version(vendor_id: str) -> int:
        last = await db.commercial_schedules.find({"vendor_id": vendor_id}).sort("version", -1).to_list(1)
        return int(last[0]["version"]) + 1 if last else 1

    async def build_agreement(vendor: dict, sched: dict, user: dict, *, amendment: bool) -> dict:
        vid = str(vendor["_id"])
        prev = await latest_agreement(vid)
        number = prev["agreement_number"] if prev else f"BUD-VND-{secrets.randbelow(999999):06d}"
        version = round(float(prev["version"]) + 0.1, 1) if (prev and amendment) else (prev["version"] if prev else 1.0)
        entity = await entity_settings()
        vendor_ctx = dict(clean(vendor), agreement_number=number, version=version)
        text = agr.agreement_text(vendor_ctx, sched, entity)
        body = {"vendor_id": vid, "agreement_number": number, "version": version,
                "status": "amendment_pending" if (prev and amendment) else "pending_vendor_acceptance",
                "commercial_schedule_id": sched["id"], "commercial_schedule_version": sched["version"],
                "effective_date": sched.get("effective_from") or iso(now_utc()),
                "expiry_date": vendor.get("agreement_end_date", ""),
                "auto_renew": bool(vendor.get("auto_renew", True)),
                "agreement_text": text, "document_hash": agr.document_hash(text),
                "created_by": user["id"], "created_at": iso(now_utc())}
        res = await db.vendor_agreements.insert_one(body)
        out = clean(await db.vendor_agreements.find_one({"_id": res.inserted_id}))
        await audit(user, "AGREEMENT_GENERATED", "vendor_agreement", out["id"],
                    {"number": number, "version": version, "schedule_version": sched["version"]})
        return out

    @api.post("/admin/vendor-profiles/{vid}/commercial-schedule")
    async def create_schedule(vid: str, payload: ScheduleIn, user: dict = Depends(manage)):
        v = await vendor_or_404(vid)
        if v.get("status") not in ("approved", "suspended"):
            raise HTTPException(status_code=400, detail="Approve the vendor before setting commercial terms.")
        body = payload.model_dump()
        if body["pricing_floor"] > body["vendor_net_rate"]:
            raise HTTPException(status_code=400, detail="Pricing floor cannot exceed the vendor net rate.")
        version = await next_version(vid)
        body.update({"vendor_id": vid, "version": version, "status": "pending",
                     "effective_from": body["effective_from"] or iso(now_utc()),
                     "created_by": user["id"], "created_by_name": user.get("full_name", ""),
                     "created_at": iso(now_utc())})
        res = await db.commercial_schedules.insert_one(body)
        sched = clean(await db.commercial_schedules.find_one({"_id": res.inserted_id}))
        await audit(user, "COMMERCIAL_SCHEDULE_CREATED", "commercial_schedule", sched["id"],
                    {"vendor_id": vid, "version": version, "summary": schedule_summary(sched)})
        ag = await build_agreement(v, sched, user, amendment=version > 1)
        if v.get("user_id"):
            await notify(v["user_id"], "Your Buddilio agreement is ready",
                         f"Review and accept {ag['agreement_number']} v{ag['version']}.",
                         "vendor", "/vendor/agreement")
        return {"schedule": sched, "agreement": ag}

    @api.post("/admin/vendor-agreements/{aid}/amend")
    async def amend_agreement(aid: str, payload: ScheduleIn, user: dict = Depends(manage)):
        ag = await db.vendor_agreements.find_one({"_id": oid(aid, "agreement")})
        if not ag:
            raise HTTPException(status_code=404, detail="Agreement not found.")
        v = await vendor_or_404(ag["vendor_id"])
        old = clean(await db.commercial_schedules.find_one({"_id": oid(ag["commercial_schedule_id"])}))
        body = payload.model_dump()
        version = await next_version(ag["vendor_id"])
        body.update({"vendor_id": ag["vendor_id"], "version": version, "status": "pending",
                     "effective_from": body["effective_from"] or iso(now_utc()),
                     "created_by": user["id"], "created_by_name": user.get("full_name", ""),
                     "created_at": iso(now_utc()), "supersedes_version": old["version"]})
        res = await db.commercial_schedules.insert_one(body)
        new = clean(await db.commercial_schedules.find_one({"_id": res.inserted_id}))
        changes = diff_schedules(old, new)
        material = any(c["field"] in agr.MATERIAL_FIELDS for c in changes)
        await audit(user, "COMMERCIAL_SCHEDULE_CHANGED", "commercial_schedule", new["id"],
                    {"vendor_id": ag["vendor_id"], "changes": changes, "material": material,
                     "reason": payload.change_reason})
        newag = await build_agreement(v, new, user, amendment=True)
        await db.vendor_agreements.update_one({"_id": ag["_id"]},
                                             {"$set": {"status": "superseded" if material else ag["status"]}})
        if v.get("user_id"):
            await notify(v["user_id"], "Commercial terms updated",
                         "Please review and accept your revised Buddilio commercial terms.",
                         "vendor", "/vendor/agreement")
        await send_tpl("vendor_terms_amended", v.get("email", ""), {
            "first_name": first_name(v.get("contact_person", "")),
            "agreement_number": newag["agreement_number"], "version": str(newag["version"]),
            "changes": "<br/>".join(f"{c['label']}: {c['from']} → {c['to']}" for c in changes) or "Minor updates",
            "effective_date": str(new["effective_from"])[:10],
            "agreement_url": f"{site_url()}/vendor/agreement"})
        return {"schedule": new, "agreement": newag, "changes": changes, "material": material}

    @api.post("/admin/vendor-agreements/{aid}/suspend")
    async def suspend_agreement(aid: str, payload: TerminateIn, user: dict = Depends(manage)):
        ag = await db.vendor_agreements.find_one({"_id": oid(aid, "agreement")})
        if not ag:
            raise HTTPException(status_code=404, detail="Agreement not found.")
        await db.vendor_agreements.update_one({"_id": ag["_id"]},
                                             {"$set": {"status": "suspended", "suspended_at": iso(now_utc()),
                                                       "suspend_reason": payload.reason,
                                                       "suspend_note": payload.note}})
        await db.vendor_profiles.update_one({"_id": oid(ag["vendor_id"])}, {"$set": {"status": "suspended"}})
        await audit(user, "AGREEMENT_SUSPENDED", "vendor_agreement", aid,
                    {"reason": payload.reason, "note": payload.note})
        return {"ok": True}

    @api.post("/admin/vendor-agreements/{aid}/terminate")
    async def terminate_agreement(aid: str, payload: TerminateIn, user: dict = Depends(manage)):
        ag = await db.vendor_agreements.find_one({"_id": oid(aid, "agreement")})
        if not ag:
            raise HTTPException(status_code=404, detail="Agreement not found.")
        # History is never deleted: the record is closed, not removed.
        await db.vendor_agreements.update_one({"_id": ag["_id"]},
                                             {"$set": {"status": "terminated", "terminated_at": iso(now_utc()),
                                                       "termination_reason": payload.reason,
                                                       "termination_note": payload.note}})
        await db.vendor_profiles.update_one({"_id": oid(ag["vendor_id"])}, {"$set": {"status": "terminated"}})
        await db.commercial_schedules.update_many({"vendor_id": ag["vendor_id"], "status": "active"},
                                                 {"$set": {"status": "closed",
                                                           "effective_until": iso(now_utc())}})
        await audit(user, "AGREEMENT_TERMINATED", "vendor_agreement", aid,
                    {"reason": payload.reason, "note": payload.note})
        return {"ok": True}

    @api.get("/admin/vendor-agreements")
    async def admin_agreements(status: str = "", user: dict = Depends(view)):
        q = {"status": status} if status else {}
        docs = await db.vendor_agreements.find(q).sort("created_at", -1).to_list(500)
        out = []
        for d in docs:
            row = clean(d)
            v = await db.vendor_profiles.find_one({"_id": oid(row["vendor_id"])},
                                                  {"legal_name": 1, "trade_name": 1, "vendor_kind": 1,
                                                   "service_category": 1, "email": 1, "status": 1})
            sched = await db.commercial_schedules.find_one({"_id": oid(row["commercial_schedule_id"])}) \
                if row.get("commercial_schedule_id") else None
            row["vendor"] = clean(v) if v else None
            row["schedule"] = clean(sched) if sched else None
            row["commission_label"] = agr.commission_label(clean(sched)) if sched else ""
            row.pop("agreement_text", None)
            out.append(row)
        return {"items": out}

    @api.get("/admin/vendor-agreements/{aid}")
    async def admin_agreement(aid: str, user: dict = Depends(view)):
        ag = await db.vendor_agreements.find_one({"_id": oid(aid, "agreement")})
        if not ag:
            raise HTTPException(status_code=404, detail="Agreement not found.")
        v = await db.vendor_profiles.find_one({"_id": oid(ag["vendor_id"])})
        sched = await db.commercial_schedules.find_one({"_id": oid(ag["commercial_schedule_id"])}) \
            if ag.get("commercial_schedule_id") else None
        acc = await db.agreement_acceptances.find_one({"agreement_id": aid, "version": ag["version"]})
        entity = await entity_settings()
        schedules = await db.commercial_schedules.find({"vendor_id": ag["vendor_id"]}).sort("version", -1).to_list(50)
        return {"agreement": clean(ag), "vendor": clean(v), "schedule": clean(sched) if sched else None,
                "acceptance": clean(acc) if acc else None, "entity": entity,
                "schedules": [clean(s) for s in schedules],
                "commercial_rows": agr.commercial_rows(clean(sched)) if sched else [],
                "sections": agr.agreement_sections(clean(v), clean(sched) if sched else {}, entity)}

    @api.get("/admin/vendor-agreements/{aid}/audit")
    async def agreement_audit(aid: str, user: dict = Depends(require_perm("audit:view"))):
        ag = await db.vendor_agreements.find_one({"_id": oid(aid, "agreement")})
        if not ag:
            raise HTTPException(status_code=404, detail="Agreement not found.")
        ids = [aid, ag["vendor_id"]]
        scheds = await db.commercial_schedules.find({"vendor_id": ag["vendor_id"]}, {"_id": 1}).to_list(50)
        ids += [str(s["_id"]) for s in scheds]
        rows = await db.audit_logs.find({"entity_id": {"$in": ids}}).sort("created_at", -1).to_list(300)
        return {"items": [clean(r) for r in rows]}

    # ---------------- pricing ----------------
    @api.post("/admin/pricing/preview")
    async def pricing_preview(payload: PreviewIn, user: dict = Depends(view)):
        return {"preview": agr.calculate_price(payload.schedule, quantity=payload.quantity,
                                               dynamic_adjustment=payload.dynamic_adjustment,
                                               discount=payload.discount)}

    @api.get("/pricing/quote")
    async def pricing_quote(vendor_id: str, service_id: str = "", quantity: int = 1,
                            dynamic_adjustment: float = 0, discount: float = 0,
                            user: dict = Depends(get_current_user)):
        """The single pricing entry point every surface must use. Commercial terms are private:
        a vendor may only quote their own id; staff with vendors:view may quote any."""
        v = await db.vendor_profiles.find_one({"_id": oid(vendor_id, "vendor")}, {"user_id": 1})
        if not v:
            raise HTTPException(status_code=404, detail="Vendor not found.")
        staff = user["role"] == "admin" or "vendors:view" in deps["perms_of"](user)
        if not staff and v.get("user_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Those commercial terms aren't yours.")
        sched = await active_schedule(vendor_id, service_id)
        if not sched:
            raise HTTPException(status_code=404, detail="No active commercial schedule for that vendor.")
        return {"quote": agr.calculate_price(sched, quantity=quantity,
                                             dynamic_adjustment=dynamic_adjustment, discount=discount),
                "settlement_cycle": sched.get("settlement_cycle", "T+7"),
                "cancellation_policy": sched.get("cancellation_policy", "")}

    @api.get("/bookings/{oid_}/commercials")
    async def booking_commercials(oid_: str, user: dict = Depends(get_current_user)):
        snap = await db.booking_commercial_snapshots.find_one({"booking_id": oid_})
        if not snap:
            raise HTTPException(status_code=404, detail="No commercial snapshot for that booking.")
        order = await db.orders.find_one({"_id": oid(oid_, "booking")})
        if order and order["user_id"] != user["id"] and user["role"] != "admin" \
                and "finance:view" not in deps["perms_of"](user):
            raise HTTPException(status_code=403, detail="That booking isn't yours.")
        return {"snapshot": clean(snap)}
