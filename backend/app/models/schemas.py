"""
Pydantic models matching Supabase schema exactly.

Conventions:
  *Base:   shared fields (no id, no timestamps)
  *Create: what the API / service layer accepts for inserts
  *Update: optional fields for partial updates
  *Read:   full DB row (API response shape)

Decimal for all monetary/numeric fields — never float on financial data.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Enums matching CHECK constraints
# ---------------------------------------------------------------------------

class InvoiceType(str, Enum):
    payable    = "payable"
    receivable = "receivable"


class InvoiceStatus(str, Enum):
    draft           = "draft"
    sent            = "sent"
    unpaid          = "unpaid"
    partially_paid  = "partially_paid"
    paid            = "paid"
    overdue         = "overdue"


class AuditAction(str, Enum):
    create = "create"
    update = "update"
    delete = "delete"


class Severity(str, Enum):
    low    = "low"
    medium = "medium"
    high   = "high"


# ---------------------------------------------------------------------------
# State machine per invoice type
# Enforced in service code, not DB constraints.
# ---------------------------------------------------------------------------

PAYABLE_TRANSITIONS: dict[str, list[str]] = {
    "unpaid":          ["partially_paid", "paid", "overdue"],
    "partially_paid":  ["paid", "overdue"],
    "overdue":         ["paid", "partially_paid"],
    "paid":            [],  # terminal
}

RECEIVABLE_TRANSITIONS: dict[str, list[str]] = {
    "draft":           ["sent"],
    "sent":            ["paid", "partially_paid", "overdue"],
    "partially_paid":  ["paid", "overdue"],
    "overdue":         ["paid", "partially_paid"],
    "paid":            [],  # terminal
}


def get_valid_transitions(invoice_type: str, current_status: str) -> list[str]:
    if invoice_type == "payable":
        return PAYABLE_TRANSITIONS.get(current_status, [])
    return RECEIVABLE_TRANSITIONS.get(current_status, [])


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

class CompanyBase(BaseModel):
    name:                   str
    domain:                 str | None = None
    country:                str | None = None
    default_tax_rate:       Decimal | None = Decimal("0")
    address:                str | None = None
    phone:                  str | None = None
    email:                  str | None = None
    tax_id:                 str | None = None
    logo_url:               str | None = None
    invoice_primary_color:  str | None = None
    invoice_accent_color:   str | None = None
    invoice_text_color:     str | None = None
    invoice_footer_text:    str | None = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name:                   str | None = None
    domain:                 str | None = None
    country:                str | None = None
    default_tax_rate:       Decimal | None = None
    address:                str | None = None
    phone:                  str | None = None
    email:                  str | None = None
    tax_id:                 str | None = None
    logo_url:               str | None = None
    invoice_primary_color:  str | None = None
    invoice_accent_color:   str | None = None
    invoice_text_color:     str | None = None
    invoice_footer_text:    str | None = None


class CompanyRead(CompanyBase):
    id:         uuid.UUID
    created_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------

class AddressBase(BaseModel):
    street:      str | None = None
    city:        str | None = None
    postal_code: str | None = None
    country:     str | None = None
    state:       str | None = None


class AddressCreate(AddressBase):
    company_id: uuid.UUID
    client_id:  uuid.UUID | None = None
    vendor_id:  uuid.UUID | None = None


class AddressRead(AddressBase):
    id:         uuid.UUID
    company_id: uuid.UUID
    created_at: datetime | None = None
    deleted_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------

class VendorBase(BaseModel):
    name:   str
    tax_id: str
    email:  str | None = None
    phone:  str | None = None


class VendorCreate(VendorBase):
    company_id: uuid.UUID


class VendorUpdate(BaseModel):
    name:           str | None = None
    tax_id:         str | None = None
    email:          str | None = None
    phone:          str | None = None
    credit_balance: Decimal | None = None


class VendorRead(VendorBase):
    id:             uuid.UUID
    company_id:     uuid.UUID
    credit_balance: Decimal = Decimal("0")
    created_at:     datetime | None = None
    deleted_at:     datetime | None = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

class ClientBase(BaseModel):
    name:   str
    tax_id: str
    email:  str | None = None
    phone:  str | None = None


class ClientCreate(ClientBase):
    company_id: uuid.UUID


class ClientUpdate(BaseModel):
    name:           str | None = None
    tax_id:         str | None = None
    email:          str | None = None
    phone:          str | None = None
    credit_balance: Decimal | None = None


class ClientRead(ClientBase):
    id:             uuid.UUID
    company_id:     uuid.UUID
    credit_balance: Decimal = Decimal("0")
    created_at:     datetime | None = None
    deleted_at:     datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class ClientCreateWithAddress(BaseModel):
    """
    Request model for POST /api/v1/clients.
    Accepts an optional nested address block.
    company_id is injected server-side from settings.
    """
    name:    str
    tax_id:  str
    email:   str | None = None
    phone:   str | None = None
    address: AddressBase | None = None


class ClientReadWithAddress(ClientRead):
    """
    Response model for POST /api/v1/clients.
    Mirrors ClientRead and appends the created address if one was provided.
    """
    address: AddressRead | None = None

# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

class InvoiceBase(BaseModel):
    invoice_number:    str
    issue_date:        date
    due_date:          date | None = None
    currency:          str
    tax_percent:       Decimal
    payment_method:    str | None = None
    description:       str | None = None
    subtotal:          Decimal | None = None
    total_tax:         Decimal | None = None
    grand_total:       Decimal | None = None
    discount:          Decimal = Decimal("0")
    status:            InvoiceStatus = InvoiceStatus.unpaid
    invoice_type:      InvoiceType = InvoiceType.payable
    confidence_score:  Decimal | None = None
    amount_paid_so_far: Decimal = Decimal("0")


class InvoiceCreate(InvoiceBase):
    company_id:         uuid.UUID
    vendor_id:          uuid.UUID | None = None
    client_id:          uuid.UUID | None = None
    vendor_address_id:  uuid.UUID | None = None
    client_address_id:  uuid.UUID | None = None


class InvoiceUpdate(BaseModel):
    invoice_number:    str | None = None
    issue_date:        date | None = None
    due_date:          date | None = None
    currency:          str | None = None
    tax_percent:       Decimal | None = None
    payment_method:    str | None = None
    description:       str | None = None
    vendor_id:         uuid.UUID | None = None
    client_id:         uuid.UUID | None = None
    vendor_address_id: uuid.UUID | None = None
    client_address_id: uuid.UUID | None = None
    subtotal:          Decimal | None = None
    total_tax:         Decimal | None = None
    grand_total:       Decimal | None = None
    discount:          Decimal | None = None
    status:            InvoiceStatus | None = None
    confidence_score:  Decimal | None = None


class InvoiceRead(InvoiceBase):
    id:                uuid.UUID
    company_id:        uuid.UUID
    vendor_id:         uuid.UUID | None = None
    client_id:         uuid.UUID | None = None
    vendor_address_id: uuid.UUID | None = None
    client_address_id: uuid.UUID | None = None
    created_at:        datetime | None = None
    updated_at:        datetime | None = None
    deleted_at:        datetime | None = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Line Items
# ---------------------------------------------------------------------------

class LineItemBase(BaseModel):
    description:   str
    quantity:      Decimal
    unit_price:    Decimal
    line_subtotal: Decimal
    discount:      Decimal = Decimal("0")


class LineItemCreate(LineItemBase):
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None


class LineItemRead(LineItemBase):
    id:         uuid.UUID
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

class PaymentBase(BaseModel):
    payment_date: date
    amount:       Decimal
    method:       str | None = None
    reference:    str | None = None


class PaymentCreate(PaymentBase):
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None


class PaymentRead(PaymentBase):
    id:         uuid.UUID
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    created_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Invoice Raw Documents
# ---------------------------------------------------------------------------

class InvoiceRawDocumentBase(BaseModel):
    raw_text:        str
    extraction_json: dict[str, Any]
    schema_version:  str | None = None


class InvoiceRawDocumentCreate(InvoiceRawDocumentBase):
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None


class InvoiceRawDocumentRead(InvoiceRawDocumentBase):
    id:           uuid.UUID
    company_id:   uuid.UUID
    invoice_id:   uuid.UUID | None = None
    storage_path: str | None = None
    created_at:   datetime | None = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Audit Logs (read-only from API)
# ---------------------------------------------------------------------------

class AuditLogRead(BaseModel):
    id:           uuid.UUID
    company_id:   uuid.UUID
    table_name:   str
    record_id:    uuid.UUID
    action:       AuditAction | None = None
    performed_by: uuid.UUID | None = None
    performed_at: datetime | None = None
    old_data:     dict[str, Any] | None = None
    new_data:     dict[str, Any] | None = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Compliance Flags
# ---------------------------------------------------------------------------

class ComplianceFlagBase(BaseModel):
    flag_type: str | None = None
    severity:  Severity | None = None
    reason:    str | None = None


class ComplianceFlagCreate(ComplianceFlagBase):
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None


class ComplianceFlagRead(ComplianceFlagBase):
    id:         uuid.UUID
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    created_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Credit Notes
# ---------------------------------------------------------------------------

class CreditNoteBase(BaseModel):
    reason: str | None = None
    amount: Decimal


class CreditNoteCreate(CreditNoteBase):
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None


class CreditNoteRead(CreditNoteBase):
    id:         uuid.UUID
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    created_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------

class RefundBase(BaseModel):
    amount: Decimal


class RefundCreate(RefundBase):
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    payment_id: uuid.UUID | None = None


class RefundRead(RefundBase):
    id:         uuid.UUID
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    payment_id: uuid.UUID | None = None
    created_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Payment Allocation (API request/response, not a DB table)
# ---------------------------------------------------------------------------

class AllocationRequest(BaseModel):
    entity_id:    uuid.UUID
    entity_type:  str  # 'client' | 'vendor'
    amount:       Decimal
    currency:     str
    method:       str | None = None
    reference:    str | None = None
    payment_date: date


class AllocationDetail(BaseModel):
    invoice_id:       uuid.UUID
    invoice_number:   str
    amount_applied:   Decimal
    previous_status:  str
    new_status:       str
    remaining_balance: Decimal


class AllocationResult(BaseModel):
    total_amount:          Decimal
    allocated_amount:      Decimal
    overpayment_credited:  Decimal
    allocations:           list[AllocationDetail]
    entity_credit_balance: Decimal


# ---------------------------------------------------------------------------
# Settings (API request/response)
# ---------------------------------------------------------------------------

class SettingsUpdate(BaseModel):
    name:             str | None = None
    country:          str | None = None
    default_tax_rate: Decimal | None = None
    address:          str | None = None
    phone:            str | None = None
    email:            str | None = None
    tax_id:           str | None = None


class SettingsPasswordSet(BaseModel):
    password: str


# ---------------------------------------------------------------------------
# Webhook (future bank integration)
# ---------------------------------------------------------------------------

class PaymentWebhookRequest(BaseModel):
    payer_reference: str
    amount:          Decimal
    currency:        str
    reference:       str
    timestamp:       datetime