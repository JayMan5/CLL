"""Privacy-first WhatsApp Cloud API adapter for CourtLOG.

Outbound notices are individual approved templates only. Court/case identifiers,
hearing dates, and reasons are deliberately excluded from the provider payload.
The adapter is disabled by default and never sends through Cloud API in demo mode.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("courtlog.whatsapp")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_TEMPLATE_NAME = re.compile(r"^[a-z0-9_]{1,512}$")
_API_VERSION = re.compile(r"^v\d+\.\d+$")


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "true" if default else "false").strip().lower() in {"1", "true", "yes", "on"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_whatsapp_phone(value: str) -> str:
    """Normalize an E.164 number; Nigerian local forms remain convenient for staff."""
    if not isinstance(value, str) or not re.fullmatch(r"[+0-9\s().-]+", value.strip()):
        raise ValueError("Enter a valid international phone number")
    normalized = re.sub(r"[\s().-]", "", value.strip())
    if normalized.startswith("00"):
        normalized = "+" + normalized[2:]
    elif normalized.startswith("0"):
        normalized = "+234" + normalized[1:]
    elif normalized.startswith("234"):
        normalized = "+" + normalized
    elif not normalized.startswith("+"):
        normalized = "+" + normalized
    if not _E164.fullmatch(normalized):
        raise ValueError("Enter a valid E.164 phone number, such as +2348031234567")
    return normalized


def mask_phone(value: str) -> str:
    """Return only a non-reversible display hint; never log or return a full number."""
    digits = re.sub(r"\D", "", str(value or ""))
    return f"••••{digits[-4:]}" if len(digits) >= 4 else "••••"


def _consent_key() -> str:
    return os.getenv("WHATSAPP_CONSENT_HASH_KEY", "").strip()


def hash_phone(value: str) -> str:
    """Create a stable keyed lookup token so consent tables do not store phone numbers."""
    key = _consent_key()
    if len(key.encode("utf-8")) < 32:
        raise ValueError("WHATSAPP_CONSENT_HASH_KEY must contain at least 32 bytes")
    phone = normalize_whatsapp_phone(value)
    return hmac.new(key.encode("utf-8"), phone.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class WhatsAppConfig:
    enabled: bool
    demo_mode: bool
    access_token: str
    phone_number_id: str
    api_version: str
    template_name: str
    template_language: str
    app_secret: str
    webhook_verify_token: str
    consent_hash_key: str
    consent_notice_version: str

    @classmethod
    def from_environment(cls) -> "WhatsAppConfig":
        return cls(
            enabled=_env_bool("WHATSAPP_ENABLED"),
            demo_mode=_env_bool("DEMO_MODE"),
            access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip(),
            phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
            api_version=os.getenv("WHATSAPP_API_VERSION", "v26.0").strip(),
            template_name=os.getenv("WHATSAPP_TEMPLATE_NAME", "").strip(),
            template_language=os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en").strip(),
            app_secret=os.getenv("WHATSAPP_APP_SECRET", "").strip(),
            webhook_verify_token=os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "").strip(),
            consent_hash_key=os.getenv("WHATSAPP_CONSENT_HASH_KEY", "").strip(),
            consent_notice_version=os.getenv("WHATSAPP_CONSENT_NOTICE_VERSION", "courtlog-demo-v1").strip(),
        )

    def missing_configuration(self) -> list[str]:
        missing: list[str] = []
        if not self.access_token:
            missing.append("WHATSAPP_ACCESS_TOKEN")
        if not self.phone_number_id or not self.phone_number_id.isdigit():
            missing.append("WHATSAPP_PHONE_NUMBER_ID")
        if not _API_VERSION.fullmatch(self.api_version):
            missing.append("WHATSAPP_API_VERSION")
        if not _TEMPLATE_NAME.fullmatch(self.template_name):
            missing.append("WHATSAPP_TEMPLATE_NAME")
        if not self.template_language or len(self.template_language) > 35:
            missing.append("WHATSAPP_TEMPLATE_LANGUAGE")
        if len(self.consent_hash_key.encode("utf-8")) < 32:
            missing.append("WHATSAPP_CONSENT_HASH_KEY (32+ bytes)")
        if not self.app_secret:
            missing.append("WHATSAPP_APP_SECRET")
        if not self.webhook_verify_token:
            missing.append("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
        return missing

    def cloud_ready(self) -> bool:
        return self.enabled and not self.demo_mode and not self.missing_configuration()


def get_public_status() -> Dict[str, Any]:
    """Expose integration readiness without returning any configured secret values."""
    config = WhatsAppConfig.from_environment()
    if config.demo_mode:
        mode = "demo_simulation"
        message = "Demo mode only. No messages are sent to WhatsApp."
    elif not config.enabled:
        mode = "disabled"
        message = "Cloud API delivery is disabled."
    elif config.missing_configuration():
        mode = "misconfigured"
        message = "Cloud API delivery is enabled but required server settings are incomplete."
    else:
        mode = "cloud_api"
        message = "Cloud API settings are present. Meta account, template approval, and recipient eligibility are not independently verified by CourtLOG."
    return {
        "mode": mode,
        "ready": config.cloud_ready(),
        "enabled": config.enabled,
        "demo_mode": config.demo_mode,
        "provider": "Meta WhatsApp Cloud API" if mode == "cloud_api" else None,
        "template_name": config.template_name or None,
        "webhook_ready": bool(config.app_secret and config.webhook_verify_token),
        "consent_store_ready": len(config.consent_hash_key.encode("utf-8")) >= 32,
        "missing": config.missing_configuration() if config.enabled and not config.demo_mode else [],
        "message": message,
    }


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Verify Meta's SHA-256 signature over the exact raw request body."""
    secret = os.getenv("WHATSAPP_APP_SECRET", "").strip()
    if not secret or not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def webhook_verification_token() -> str:
    return os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "").strip()


def _case_phone(case: Dict[str, Any], recipient_role: str) -> Optional[str]:
    field = f"{recipient_role}_phone"
    contact = case.get("party_contact") if isinstance(case.get("party_contact"), dict) else {}
    value = contact.get(field) or case.get(field)
    return value if isinstance(value, str) and value.strip() else None


def _recipient_status(database, phone: str) -> tuple[str, str]:
    """Return initial message status and keyed recipient token without storing a number."""
    config = WhatsAppConfig.from_environment()
    if len(config.consent_hash_key.encode("utf-8")) < 32:
        return "disabled", ""
    try:
        recipient_hash = hash_phone(phone)
    except ValueError:
        return "disabled", ""
    preference = database.get_whatsapp_preference(recipient_hash)
    if not preference or preference.get("status") != "opted_in":
        return "suppressed_no_consent", recipient_hash
    if config.demo_mode:
        return "simulated", recipient_hash
    if not config.cloud_ready():
        return "disabled", recipient_hash
    return "queued", recipient_hash


def _insert_message(
    database,
    *,
    idempotency_key: str,
    case_id: str,
    recipient_role: str,
    phone: str,
    recipient_hash: str,
    trigger_type: str,
    status: str,
) -> tuple[Dict[str, Any], bool]:
    config = WhatsAppConfig.from_environment()
    created_at = _now()
    return database.create_whatsapp_message({
        "message_id": uuid.uuid4().hex,
        "idempotency_key": idempotency_key,
        "case_id": case_id,
        "recipient_role": recipient_role,
        "recipient_hash": recipient_hash,
        "recipient_masked": mask_phone(phone),
        "template_name": config.template_name or "unconfigured",
        "trigger_type": trigger_type,
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
    })


def _send_template(phone: str) -> Dict[str, Optional[str]]:
    config = WhatsAppConfig.from_environment()
    if not config.cloud_ready():
        return {"status": "disabled", "provider_message_id": None, "error_code": "configuration_incomplete", "error_message": "Required Cloud API or webhook settings are incomplete."}
    try:
        phone = normalize_whatsapp_phone(phone)
    except ValueError:
        return {"status": "failed", "provider_message_id": None, "error_code": "invalid_recipient", "error_message": "Recipient number is no longer valid."}

    # The approved template must be generic: no case number, date, or hearing reason.
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "template",
        "template": {
            "name": config.template_name,
            "language": {"code": config.template_language},
        },
    }
    url = f"https://graph.facebook.com/{config.api_version}/{config.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {config.access_token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=(5, 20), allow_redirects=False)
    except requests.exceptions.RequestException as exc:
        # A timeout may happen after the provider accepted the message. Never blindly retry.
        logger.warning("WhatsApp provider outcome is uncertain (%s)", type(exc).__name__)
        return {"status": "unknown", "provider_message_id": None, "error_code": "provider_outcome_unknown", "error_message": "The provider outcome could not be confirmed; verify delivery before retrying."}

    try:
        body = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        body = {}

    if 200 <= response.status_code < 300:
        messages = body.get("messages") if isinstance(body, dict) else None
        provider_id = messages[0].get("id") if isinstance(messages, list) and messages and isinstance(messages[0], dict) else None
        if provider_id:
            return {"status": "accepted", "provider_message_id": str(provider_id), "error_code": None, "error_message": None}
        return {"status": "unknown", "provider_message_id": None, "error_code": "missing_provider_id", "error_message": "The provider response did not include a message identifier."}

    error = body.get("error", {}) if isinstance(body, dict) else {}
    error_code = error.get("code") if isinstance(error, dict) else None
    # Do not persist the provider's raw body; errors can contain request details.
    if response.status_code == 429:
        return {"status": "failed", "provider_message_id": None, "error_code": str(error_code or "rate_limited"), "error_message": "Provider rate limited the request; no automatic retry was made."}
    return {"status": "failed", "provider_message_id": None, "error_code": str(error_code or f"http_{response.status_code}"), "error_message": "The provider rejected the request; review configuration and message-template eligibility."}


def deliver_whatsapp_message(database, message_id: str) -> Dict[str, Any]:
    """Claim and send a queued message once, rechecking current consent and contact."""
    message = database.get_whatsapp_message(message_id)
    if not message or message.get("status") != "queued":
        return {"status": message.get("status") if message else "missing"}
    case = database.get_case(message["case_id"])
    phone = _case_phone(case or {}, message["recipient_role"])
    if not case or not phone:
        database.update_whatsapp_message(message_id, "failed", _now(), error_code="contact_missing", error_message="The case contact is no longer available.")
        return {"status": "failed"}
    try:
        normalized = normalize_whatsapp_phone(phone)
        current_hash = hash_phone(normalized)
    except ValueError:
        database.update_whatsapp_message(message_id, "failed", _now(), error_code="recipient_unavailable", error_message="The case contact could not be verified.")
        return {"status": "failed"}
    if not hmac.compare_digest(current_hash, message["recipient_hash"]):
        database.update_whatsapp_message(message_id, "failed", _now(), error_code="contact_changed", error_message="The case contact changed after this notice was queued.")
        return {"status": "failed"}
    preference = database.get_whatsapp_preference(current_hash)
    if not preference or preference.get("status") != "opted_in":
        database.update_whatsapp_message(message_id, "suppressed_no_consent", _now(), error_code="consent_not_active", error_message="No active opt-in is recorded for this recipient.")
        return {"status": "suppressed_no_consent"}

    config = WhatsAppConfig.from_environment()
    if config.demo_mode:
        database.update_whatsapp_message(message_id, "simulated", _now())
        return {"status": "simulated"}
    if not config.cloud_ready():
        database.update_whatsapp_message(message_id, "disabled", _now(), error_code="configuration_incomplete", error_message="Required Cloud API or webhook settings are incomplete.")
        return {"status": "disabled"}
    if not database.claim_whatsapp_message(message_id, _now()):
        latest = database.get_whatsapp_message(message_id)
        return {"status": latest.get("status") if latest else "missing"}

    # Recheck immediately before the outbound provider call in case the opt-out arrived
    # while this outbox item was waiting to be claimed.
    latest_preference = database.get_whatsapp_preference(current_hash)
    if not latest_preference or latest_preference.get("status") != "opted_in":
        database.update_whatsapp_message(message_id, "suppressed_no_consent", _now(), error_code="consent_not_active", error_message="No active opt-in is recorded for this recipient.")
        return {"status": "suppressed_no_consent"}

    result = _send_template(normalized)
    database.update_whatsapp_message(
        message_id,
        str(result["status"]),
        _now(),
        provider_message_id=result.get("provider_message_id"),
        error_code=result.get("error_code"),
        error_message=result.get("error_message"),
    )
    return {"status": result["status"], "provider_message_id": result.get("provider_message_id")}


def send_adjournment_broadcast(
    case_id: str,
    next_date: str = "",
    reason_code: str = "",
    group_id: Optional[str] = None,
    *,
    event_id: Optional[str] = None,
    database=None,
    actor_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Queue one-to-one schedule prompts for contacts with an explicit current opt-in.

    The legacy date/reason/group arguments remain accepted for call compatibility, but
    none are copied into a recipient payload and no WhatsApp group is ever contacted.
    """
    if database is None:
        return {"status": "disabled", "message": "Database context is required; no notification was sent."}
    case = database.get_case(case_id)
    if not case:
        return {"status": "disabled", "message": "Case not found; no notification was sent."}

    event_id = event_id or uuid.uuid4().hex
    statuses: list[str] = []
    for recipient_role in ("counsel", "litigant"):
        phone = _case_phone(case, recipient_role)
        if not phone:
            continue
        initial_status, recipient_hash = _recipient_status(database, phone)
        idempotency_key = hashlib.sha256(
            f"adjournment:{case_id}:{event_id}:{recipient_role}".encode("utf-8")
        ).hexdigest()
        message, inserted = _insert_message(
            database,
            idempotency_key=idempotency_key,
            case_id=case_id,
            recipient_role=recipient_role,
            phone=phone,
            recipient_hash=recipient_hash,
            trigger_type="adjournment",
            status=initial_status,
        )
        if inserted and message["status"] == "queued":
            outcome = deliver_whatsapp_message(database, message["message_id"])
            statuses.append(outcome["status"])
        else:
            statuses.append(message["status"])
    return {"status": "processed", "message_statuses": statuses}


def create_manual_test_message(database, case_id: str, recipient_role: str) -> tuple[Dict[str, Any], bool]:
    """Create a generic template test against a case contact, preserving idempotency."""
    case = database.get_case(case_id)
    if not case:
        raise ValueError("Case not found")
    phone = _case_phone(case, recipient_role)
    if not phone:
        raise ValueError("Selected case contact has no phone number")
    initial_status, recipient_hash = _recipient_status(database, phone)
    if initial_status == "suppressed_no_consent":
        raise PermissionError("No active opt-in is recorded for this recipient")
    config = WhatsAppConfig.from_environment()
    if initial_status == "disabled":
        raise RuntimeError("WhatsApp delivery is not ready; check server configuration")
    event_id = uuid.uuid4().hex
    idempotency_key = hashlib.sha256(f"manual-test:{event_id}".encode("utf-8")).hexdigest()
    return _insert_message(
        database,
        idempotency_key=idempotency_key,
        case_id=case_id,
        recipient_role=recipient_role,
        phone=phone,
        recipient_hash=recipient_hash,
        trigger_type="manual_test",
        status="simulated" if config.demo_mode else "queued",
    )
