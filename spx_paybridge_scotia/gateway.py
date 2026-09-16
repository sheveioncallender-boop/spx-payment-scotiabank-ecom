"""Pure Fiserv Connect protocol. No ORM, HTTP requests, or card-data storage.

Protocol source: supplied Connect Integration Guide, section 14 (pp. 29-30)
and Appendix I (pp. 31-32). Standard signatures are bound to an immutable,
uniquely allocated request timestamp, amount, currency and merchant store.
"""

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit


class InvalidResponse(ValueError):
    """A bank message cannot be trusted or does not match its payment attempt."""


@dataclass(frozen=True)
class ExpectedPayment:
    oid: str
    amount: str
    currency: str
    txndatetime: str
    store_id: str


@dataclass(frozen=True)
class VerifiedResponse:
    outcome: str
    transaction_id: str
    approval_code: str
    status: str
    reference_number: str
    processor_code: str
    three_ds_result: str
    card_last4: str
    card_brand: str
    fingerprint: str
    signature_type: str


def amount_string(amount):
    try:
        value = Decimal(str(amount))
        if not value.is_finite() or value <= 0 or value != value.quantize(Decimal('0.01')):
            raise InvalidResponse('invalid_amount')
        return format(value, '.2f')
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InvalidResponse('invalid_amount') from exc


def public_base_url(value):
    """Fiserv notifications require HTTPS on the standard port."""
    try:
        parsed = urlsplit(value or '')
        valid = (parsed.scheme == 'https' and parsed.hostname
                 and parsed.port in (None, 443) and not parsed.username
                 and not parsed.password and parsed.path in ('', '/')
                 and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Use the public HTTPS Odoo origin on port 443, without a path or query.')
    return value.rstrip('/')


def _hmac(secret, value):
    return base64.b64encode(hmac.new(
        secret.encode('utf-8'), value.encode('utf-8'), hashlib.sha256,
    ).digest()).decode('ascii')


def request_hash(parameters, secret):
    if not secret:
        raise ValueError('A shared secret is required.')
    values = [str(parameters[key]) for key in sorted(parameters)
              if key not in ('hashExtended', 'sharedsecret')
              and parameters[key] not in (None, '')]
    return _hmac(secret, '|'.join(values))


def standard_response_hash(parameters, secret, expected, source='return'):
    # Use OUR stored request datetime and Store ID, never values selected by
    # the sender. Fiserv does not always echo storename in its response.
    parts = [parameters.get('chargetotal', ''), parameters.get('currency', ''),
             expected.txndatetime, expected.store_id]
    approval = parameters.get('approval_code', '')
    parts = parts + [approval] if source == 'notification' else [approval] + parts
    return _hmac(secret, '|'.join(parts))


def verify_response(parameters, secrets, expected, source='return'):
    if source not in ('return', 'notification'):
        raise InvalidResponse('invalid_source')
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in parameters.items()):
        raise InvalidResponse('invalid_fields')
    signature_type = source
    signature_key = 'notification_hash' if source == 'notification' else 'response_hash'
    signature = parameters.get(signature_key, '').strip().replace(' ', '+')
    if not signature:
        raise InvalidResponse('signature_missing')
    try:
        if len(base64.b64decode(signature, validate=True)) != 32:
            raise InvalidResponse('signature_invalid')
    except (ValueError, TypeError) as exc:
        raise InvalidResponse('signature_invalid') from exc
    def expected_signature(secret):
        return standard_response_hash(parameters, secret, expected, source)
    if not any(secret and hmac.compare_digest(expected_signature(secret), signature) for secret in secrets):
        raise InvalidResponse('signature_invalid')

    if parameters.get('hash_algorithm', 'HMACSHA256') != 'HMACSHA256':
        raise InvalidResponse('algorithm_mismatch')
    if not expected.oid or parameters.get('oid') != expected.oid:
        raise InvalidResponse('order_mismatch')
    if not expected.txndatetime or (parameters.get('txndatetime')
                                  and parameters['txndatetime'] != expected.txndatetime):
        raise InvalidResponse('attempt_mismatch')
    if parameters.get('storename') and parameters['storename'] != expected.store_id:
        raise InvalidResponse('store_mismatch')
    if parameters.get('currency') != expected.currency:
        raise InvalidResponse('currency_mismatch')
    if amount_string(parameters.get('chargetotal')) != amount_string(expected.amount):
        raise InvalidResponse('amount_mismatch')
    transaction_id = parameters.get('ipgTransactionId', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', transaction_id):
        transaction_id = ''

    approval = parameters.get('approval_code', '')
    reported_status = parameters.get('status', '').upper()
    # Only approval_code is authenticated. Ignore the unsigned
    # status and processor code when choosing the financial outcome.
    if approval.startswith('Y'):
        if reported_status == 'PARTIALLY APPROVED':
            raise InvalidResponse('partial_approval_not_supported')
        if parameters.get('partiallyApprovedAmount'):
            if amount_string(parameters['partiallyApprovedAmount']) != amount_string(expected.amount):
                raise InvalidResponse('partial_approval_not_supported')
        outcome = 'done'
        status = 'APPROVED'
    elif approval.startswith('?'):
        outcome = 'pending'
        status = 'WAITING'
    elif approval.startswith('N'):
        outcome = 'error'
        status = 'DECLINED'
    else:
        raise InvalidResponse('inconsistent_or_unsupported_status')

    digits = re.sub(r'\D', '', parameters.get('cardnumber', ''))
    return VerifiedResponse(
        outcome=outcome, transaction_id=transaction_id,
        approval_code=approval[:128], status=status[:32],
        reference_number=parameters.get('refnumber', '')[:128],
        processor_code=parameters.get('processor_response_code', '')[:32],
        three_ds_result=parameters.get('response_code_3dsecure', '')[:32],
        card_last4=digits[-4:] if len(digits) >= 4 else '',
        card_brand=parameters.get('ccbrand', '')[:32],
        fingerprint=hashlib.sha256(signature.encode('ascii')).hexdigest(),
        signature_type=signature_type,
    )
