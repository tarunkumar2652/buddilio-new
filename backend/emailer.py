"""Transactional email via the Emergent-managed Resend integration."""
import os
import logging
import httpx

logger = logging.getLogger("buddilio.email")

EMAIL_BASE_URL = "https://integrations.emergentagent.com"


def _brand() -> str:
    return os.environ.get("EMAIL_FROM_NAME", "Buddilio")


def wrap(title: str, body_html: str, cta_label: str = "", cta_url: str = "") -> str:
    cta = ""
    if cta_label and cta_url:
        cta = (f'<tr><td style="padding:8px 32px 32px 32px"><a href="{cta_url}" '
               'style="display:inline-block;background:#0F172A;color:#ffffff;text-decoration:none;'
               'padding:14px 26px;border-radius:999px;font-weight:700;font-size:14px">'
               f'{cta_label}</a></td></tr>')
    return f"""<!doctype html><html><body style="margin:0;background:#FAFAFA;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#FAFAFA;padding:28px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #E2E8F0;border-radius:16px;font-family:Helvetica,Arial,sans-serif;">
<tr><td style="padding:28px 32px 8px 32px;">
  <span style="display:inline-block;width:34px;height:34px;line-height:34px;text-align:center;background:#0F172A;color:#fff;border-radius:10px;font-weight:700;">B</span>
  <span style="font-size:18px;font-weight:700;color:#0F172A;margin-left:8px;vertical-align:middle;">Buddilio</span>
</td></tr>
<tr><td style="padding:16px 32px 0 32px;">
  <h1 style="margin:0;font-size:22px;color:#0F172A;">{title}</h1>
</td></tr>
<tr><td style="padding:12px 32px 8px 32px;color:#475569;font-size:15px;line-height:1.65;">{body_html}</td></tr>
{cta}
<tr><td style="padding:20px 32px;border-top:1px solid #F1F5F9;color:#94A3B8;font-size:12px;line-height:1.6;">
  Buddilio is a social discovery platform, not a dating service. Always meet in public places and never transfer money to another member.<br/>
  © Buddilio Experiences · a global social club
</td></tr>
</table></td></tr></table></body></html>"""


async def send_email(to: str, subject: str, html: str, reply_to: str = "hello@buddilio.com") -> bool:
    key = os.environ.get("EMERGENT_EMAIL_KEY")
    if not key or not to:
        logger.info(f"[email skipped] to={to} subject={subject}")
        return False
    payload = {"to": [to], "subject": subject, "html": html, "from_name": _brand()}
    if reply_to:
        payload["contact_email"] = reply_to
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                                     headers={"X-Email-Key": key}, json=payload)
        resp.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        logger.error(f"Email send failed: {e.response.status_code} {e.response.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return False
