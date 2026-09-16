"""Exercise Odoo 19's real field-fetch selection against legacy-schema tables.

SQLite supplies disposable in-memory tables so selecting an absent column fails
without a PostgreSQL service. This reproduces the pre-upgrade read, not a full
Odoo registry/module migration. No merchant data or external calls are used.
"""
import copy
import sqlite3
import unittest
from types import SimpleNamespace

from odoo import models
from odoo.addons.payment.models.payment_provider import PaymentProvider as NativeProvider
from odoo.addons.payment.models.payment_transaction import PaymentTransaction as NativeTransaction

from ..models.payment_provider import PaymentProvider
from ..models.payment_transaction import PaymentTransaction


PROVIDER_ADDED_FIELDS = {
    'scotia_sandbox_usd_override', 'scotia_display_mode', 'scotia_show_branding',
    'scotia_language', 'scotia_log_summary',
}
TRANSACTION_ADDED_FIELDS = {
    'scotia_original_currency_alpha', 'scotia_sandbox_override', 'scotia_display_mode',
    'scotia_show_branding', 'scotia_language', 'scotia_handoff_started',
}


class LegacySchemaRecord:
    """Small database boundary for BaseModel._fetch_field, using real Fields."""

    def __init__(self, native, extension, native_field, added):
        self.env = SimpleNamespace(context={})
        self._fields = {native_field: copy.copy(getattr(native, native_field))}
        self._fields.update({field.name: copy.copy(field) for field in extension._field_definitions
                             if field.name.startswith('scotia_') and field.store and field.column_type})
        self.added = added
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        old_fields = [name for name in self._fields if name not in added]
        self.db.execute('CREATE TABLE legacy (' + ', '.join(f'"{name}" TEXT' for name in old_fields) + ')')
        self.db.execute('INSERT INTO legacy DEFAULT VALUES')
        self.db.execute(f'UPDATE legacy SET "{native_field}" = ?', ('existing-record',))
        self.cache = {}
        self.fetched = []

    def _has_field_access(self, field, operation):
        return True

    def fetch(self, names):
        self.fetched = list(names)
        # Qualified columns make absent names fail (no SQLite quoted-literal fallback).
        row = self.db.execute('SELECT ' + ', '.join(f'legacy."{name}"' for name in names) + ' FROM legacy').fetchone()
        self.cache.update(dict(row))

    def read_field(self, name):
        models.BaseModel._fetch_field(self, self._fields[name])
        return self.cache[name]

    def add_new_columns(self):
        for name in self.added:
            field = self._fields[name]
            self.db.execute(f'ALTER TABLE legacy ADD COLUMN "{name}" TEXT')
            default = field.default(None) if field.default else None
            self.db.execute(f'UPDATE legacy SET "{name}" = ?', (default,))


class TestUpgradePrefetch(unittest.TestCase):
    def record(self, transaction=False):
        args = ((NativeTransaction, PaymentTransaction, 'reference', TRANSACTION_ADDED_FIELDS)
                if transaction else (NativeProvider, PaymentProvider, 'module_id', PROVIDER_ADDED_FIELDS))
        record = LegacySchemaRecord(*args)
        self.addCleanup(record.db.close)
        return record

    def test_unpatched_provider_read_reproduces_reported_missing_column(self):
        record = self.record()
        record._fields['scotia_sandbox_usd_override'].prefetch = True
        with self.assertRaisesRegex(sqlite3.OperationalError, 'scotia_sandbox_usd_override'):
            record.read_field('module_id')

    def test_native_provider_read_succeeds_before_columns_exist(self):
        record = self.record()
        self.assertEqual(record.read_field('module_id'), 'existing-record')
        self.assertFalse(PROVIDER_ADDED_FIELDS.intersection(record.fetched))

    def test_provider_settings_remain_stored_and_readable_after_schema_update(self):
        record = self.record()
        record.add_new_columns()
        expected = {'scotia_sandbox_usd_override': '1', 'scotia_display_mode': 'redirect',
                    'scotia_show_branding': '1', 'scotia_language': 'en_GB', 'scotia_log_summary': '1'}
        for name, value in expected.items():
            with self.subTest(field=name):
                self.assertTrue(record._fields[name].store)
                self.assertEqual(record.read_field(name), value)
                self.assertEqual(record.fetched, [name])

    def test_unpatched_transaction_read_reproduces_missing_column(self):
        record = self.record(transaction=True)
        record._fields['scotia_original_currency_alpha'].prefetch = True
        with self.assertRaisesRegex(sqlite3.OperationalError, 'scotia_original_currency_alpha'):
            record.read_field('reference')

    def test_native_transaction_read_succeeds_before_columns_exist(self):
        record = self.record(transaction=True)
        self.assertEqual(record.read_field('reference'), 'existing-record')
        self.assertFalse(TRANSACTION_ADDED_FIELDS.intersection(record.fetched))
