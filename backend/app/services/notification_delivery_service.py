"""
Notification Delivery Service
------------------------------
Sends external email and SMS notifications to clients/vendors.
Completely separate from notification_service.py which handles
internal DB notifications (the bell icon in the UI).

Providers:
  EMAIL_PROVIDER=mock     → logs to console + audit_logs, never fails
  EMAIL_PROVIDER=sendgrid → calls SendGrid API v3

  SMS_PROVIDER=mock       → logs to console + audit_logs, never fails
  SMS_PROVIDER=twilio     → calls Twilio REST API

All sends are fire-and-forget:
  - Wrap every call in try/except
  - Delivery failure NEVER raises — never blocks parent operations
  - Every attempt (success or failure) logged to audit_logs

Template types:
  invoice_sent      — new invoice issued to client
  payment_reminder  — upcoming due date reminder
  overdue_notice    — invoice is past due
  payment_received  — payment confirmed

Usage:
  from app.services.notification_delivery_service import send_invoice_email, send_invoice_sms
  send_invoice_email(invoice, client_email, template_type="invoice_sent")
  send_invoice_sms(invoice, client_phone, template_type="overdue_notice")
"""

import logging
from datetime import datetime

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template builders
# ---------------------------------------------------------------------------

def _build_email_subject(invoice: dict, template_type: str, company_name: str) -> str:
    number  = invoice.get("invoice_number", "Unknown")
    amount  = invoice.get("grand_total")
    currency = invoice.get("currency", "")
    due     = invoice.get("due_date", "N/A")

    amount_str = f"{currency} {float(amount):.2f}" if amount is not None else "N/A"

    subjects = {
        "invoice_sent":      f"Invoice {number} from {company_name} — {amount_str} due {due}",
        "payment_reminder":  f"Reminder: Invoice {number} — {amount_str} due {due}",
        "overdue_notice":    f"OVERDUE: Invoice {number} — {amount_str} was due {due}",
        "payment_received":  f"Payment confirmed for Invoice {number} — Thank you",
    }
    return subjects.get(template_type, f"Invoice {number} — {company_name}")


def _build_email_body(invoice: dict, template_type: str, company_name: str) -> tuple[str, str]:
    """Returns (plain_text, html) tuple."""
    number   = invoice.get("invoice_number", "Unknown")
    amount   = invoice.get("grand_total")
    currency = invoice.get("currency", "")
    due      = invoice.get("due_date", "N/A")
    paid     = invoice.get("amount_paid_so_far", 0)

    amount_str  = f"{currency} {float(amount):.2f}" if amount is not None else "N/A"
    paid_str    = f"{currency} {float(paid):.2f}" if paid else None
    remaining   = (float(amount) - float(paid)) if amount and paid else None
    rem_str     = f"{currency} {remaining:.2f}" if remaining is not None else None

    if template_type == "invoice_sent":
        plain = (
            f"Dear Customer,\n\n"
            f"Please find attached Invoice {number} for {amount_str}.\n"
            f"Payment is due by {due}.\n\n"
            f"Thank you for your business.\n\n{company_name}"
        )
        html = (
            f"<p>Dear Customer,</p>"
            f"<p>Please find attached <strong>Invoice {number}</strong> for <strong>{amount_str}</strong>.</p>"
            f"<p>Payment is due by <strong>{due}</strong>.</p>"
            f"<p>Thank you for your business.</p>"
            f"<p>{company_name}</p>"
        )

    elif template_type == "payment_reminder":
        plain = (
            f"Dear Customer,\n\n"
            f"This is a friendly reminder that Invoice {number} for {amount_str} "
            f"is due on {due}.\n\n"
            f"If you have already paid, please disregard this message.\n\n{company_name}"
        )
        html = (
            f"<p>Dear Customer,</p>"
            f"<p>This is a friendly reminder that <strong>Invoice {number}</strong> "
            f"for <strong>{amount_str}</strong> is due on <strong>{due}</strong>.</p>"
            f"<p>If you have already paid, please disregard this message.</p>"
            f"<p>{company_name}</p>"
        )

    elif template_type == "overdue_notice":
        plain = (
            f"Dear Customer,\n\n"
            f"Invoice {number} for {amount_str} was due on {due} and remains unpaid"
            + (f" (balance: {rem_str})" if rem_str else "") +
            f".\n\nPlease arrange payment at your earliest convenience.\n\n{company_name}"
        )
        html = (
            f"<p>Dear Customer,</p>"
            f"<p><strong>Invoice {number}</strong> for <strong>{amount_str}</strong> "
            f"was due on <strong>{due}</strong> and remains unpaid"
            + (f" (balance: <strong>{rem_str}</strong>)" if rem_str else "") +
            f".</p>"
            f"<p>Please arrange payment at your earliest convenience.</p>"
            f"<p>{company_name}</p>"
        )

    elif template_type == "payment_received":
        plain = (
            f"Dear Customer,\n\n"
            f"We have received your payment"
            + (f" of {paid_str}" if paid_str else "") +
            f" for Invoice {number}. Thank you!\n\n{company_name}"
        )
        html = (
            f"<p>Dear Customer,</p>"
            f"<p>We have received your payment"
            + (f" of <strong>{paid_str}</strong>" if paid_str else "") +
            f" for <strong>Invoice {number}</strong>. Thank you!</p>"
            f"<p>{company_name}</p>"
        )

    else:
        plain = f"Notification regarding Invoice {number} from {company_name}."
        html  = f"<p>Notification regarding Invoice {number} from {company_name}.</p>"

    return plain, html


def _build_sms_body(invoice: dict, template_type: str, company_name: str) -> str:
    """160-char max SMS body."""
    number   = invoice.get("invoice_number", "Unknown")
    amount   = invoice.get("grand_total")
    currency = invoice.get("currency", "")
    due      = invoice.get("due_date", "N/A")
    amount_str = f"{currency}{float(amount):.2f}" if amount is not None else "N/A"

    messages = {
        "invoice_sent":     f"{company_name}: Invoice {number} {amount_str} due {due}. Please pay on time.",
        "payment_reminder": f"Reminder from {company_name}: Invoice {number} {amount_str} due {due}.",
        "overdue_notice":   f"OVERDUE: Invoice {number} {amount_str} from {company_name} was due {due}. Pay now.",
        "payment_received": f"{company_name}: Payment received for Invoice {number}. Thank you!",
    }
    msg = messages.get(template_type, f"{company_name}: Invoice {number} notification.")
    return msg[:160]


def _get_company_name() -> str:
    try:
        from app.core.config import get_settings
        settings = get_settings()
        # MVP: return a generic name; settings endpoint will provide real name
        return "Invoice System"
    except Exception:
        return "Invoice System"


# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------

class MockEmailProvider:
    def send(self, to: str, subject: str, plain: str, html: str) -> dict:
        log.info(
            f"[MOCK EMAIL] To: {to}\n"
            f"  Subject: {subject}\n"
            f"  Body: {plain[:120]}..."
        )
        return {"provider": "mock", "status": "logged", "to": to}


class MockSMSProvider:
    def send(self, to: str, body: str) -> dict:
        log.info(f"[MOCK SMS] To: {to} | Body: {body}")
        return {"provider": "mock", "status": "logged", "to": to}


# ---------------------------------------------------------------------------
# SendGrid provider
# ---------------------------------------------------------------------------

class SendGridProvider:
    def __init__(self, api_key: str, from_email: str = "noreply@invoicesystem.com"):
        self.api_key    = api_key
        self.from_email = from_email

    def send(self, to: str, subject: str, plain: str, html: str) -> dict:
        try:
            import urllib.request
            import json

            payload = {
                "personalizations": [{"to": [{"email": to}]}],
                "from":    {"email": self.from_email},
                "subject": subject,
                "content": [
                    {"type": "text/plain", "value": plain},
                    {"type": "text/html",  "value": html},
                ],
            }
            data = json.dumps(payload).encode("utf-8")
            req  = urllib.request.Request(
                "https://api.sendgrid.com/v3/mail/send",
                data=data,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type":  "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
            log.info(f"SendGrid email sent to {to}: HTTP {status}")
            return {"provider": "sendgrid", "status": "sent", "to": to, "http_status": status}
        except Exception as e:
            log.error(f"SendGrid send failed to {to}: {e}")
            raise


# ---------------------------------------------------------------------------
# Twilio provider
# ---------------------------------------------------------------------------

class TwilioSMSProvider:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.account_sid = account_sid
        self.auth_token  = auth_token
        self.from_number = from_number

    def send(self, to: str, body: str) -> dict:
        try:
            import urllib.request
            import urllib.parse
            import base64

            url  = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
            data = urllib.parse.urlencode({
                "From": self.from_number,
                "To":   to,
                "Body": body,
            }).encode("utf-8")
            credentials = base64.b64encode(
                f"{self.account_sid}:{self.auth_token}".encode()
            ).decode()
            req = urllib.request.Request(
                url, data=data,
                headers={"Authorization": f"Basic {credentials}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
            log.info(f"Twilio SMS sent to {to}: HTTP {status}")
            return {"provider": "twilio", "status": "sent", "to": to, "http_status": status}
        except Exception as e:
            log.error(f"Twilio send failed to {to}: {e}")
            raise


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def _get_email_provider():
    from app.core.config import get_settings
    settings = get_settings()
    provider = getattr(settings, "EMAIL_PROVIDER", "mock")

    if provider == "sendgrid":
        api_key = getattr(settings, "SENDGRID_API_KEY", "")
        if not api_key:
            log.warning("EMAIL_PROVIDER=sendgrid but SENDGRID_API_KEY not set — falling back to mock")
            return MockEmailProvider()
        return SendGridProvider(api_key=api_key)

    return MockEmailProvider()


def _get_sms_provider():
    from app.core.config import get_settings
    settings = get_settings()
    provider = getattr(settings, "SMS_PROVIDER", "mock")

    if provider == "twilio":
        sid    = getattr(settings, "TWILIO_ACCOUNT_SID", "")
        token  = getattr(settings, "TWILIO_AUTH_TOKEN", "")
        number = getattr(settings, "TWILIO_FROM_NUMBER", "")
        if not all([sid, token, number]):
            log.warning("SMS_PROVIDER=twilio but Twilio credentials incomplete — falling back to mock")
            return MockSMSProvider()
        return TwilioSMSProvider(sid, token, number)

    return MockSMSProvider()


# ---------------------------------------------------------------------------
# Audit logging for delivery attempts
# ---------------------------------------------------------------------------

def _log_delivery_attempt(
    db,
    company_id: str,
    invoice_id: str | None,
    channel: str,
    recipient: str,
    template_type: str,
    result: dict | None,
    error: str | None,
) -> None:
    if db is None:
        return
    try:
        db.table("audit_logs").insert({
            "company_id":   company_id,
            "table_name":   "notifications",
            "record_id":    invoice_id or company_id,
            "action":       "create",
            "performed_by": None,
            "old_data":     None,
            "new_data": {
                "channel":       channel,
                "recipient":     recipient,
                "template_type": template_type,
                "status":        "sent" if result else "failed",
                "error":         error,
                "timestamp":     datetime.utcnow().isoformat(),
            },
        }).execute()
    except Exception as e:
        log.error(f"Failed to log delivery attempt to audit_logs: {e}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_invoice_email(
    invoice: dict,
    recipient_email: str,
    template_type: str = "invoice_sent",
    db=None,
    company_id: str | None = None,
) -> None:
    """
    Send an invoice-related email. Fire-and-forget — never raises.

    Args:
        invoice:        Invoice dict (needs invoice_number, grand_total, due_date, currency).
        recipient_email: Destination email address.
        template_type:  'invoice_sent' | 'payment_reminder' | 'overdue_notice' | 'payment_received'
        db:             Supabase client (optional — for audit logging).
        company_id:     Company UUID (optional — for audit logging).
    """
    company_name = _get_company_name()
    subject      = _build_email_subject(invoice, template_type, company_name)
    plain, html  = _build_email_body(invoice, template_type, company_name)

    result = None
    error  = None

    try:
        provider = _get_email_provider()
        result   = provider.send(recipient_email, subject, plain, html)
    except Exception as e:
        error = str(e)
        log.error(f"Email delivery failed to {recipient_email} ({template_type}): {e}")

    _log_delivery_attempt(
        db, company_id or "",
        invoice.get("id"),
        "email", recipient_email, template_type, result, error,
    )


def send_invoice_sms(
    invoice: dict,
    recipient_phone: str,
    template_type: str = "invoice_sent",
    db=None,
    company_id: str | None = None,
) -> None:
    """
    Send an invoice-related SMS. Fire-and-forget — never raises.

    Args:
        invoice:         Invoice dict.
        recipient_phone: Destination phone number (E.164 format: +1234567890).
        template_type:   Same types as email.
        db:              Supabase client (optional — for audit logging).
        company_id:      Company UUID (optional — for audit logging).
    """
    company_name = _get_company_name()
    body         = _build_sms_body(invoice, template_type, company_name)

    result = None
    error  = None

    try:
        provider = _get_sms_provider()
        result   = provider.send(recipient_phone, body)
    except Exception as e:
        error = str(e)
        log.error(f"SMS delivery failed to {recipient_phone} ({template_type}): {e}")

    _log_delivery_attempt(
        db, company_id or "",
        invoice.get("id"),
        "sms", recipient_phone, template_type, result, error,
    )