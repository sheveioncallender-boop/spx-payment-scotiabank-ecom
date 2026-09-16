#!/usr/bin/env python3
"""Offline syntax/protocol checks, plus real Odoo imports when --odoo-root is set.

This command does not install a database and does not claim to execute the
Enterprise accounting integration tests in tests/test_native_flow.py.
"""
import argparse
import ast
import importlib.util
import pathlib
import sys
import types
import unittest
import xml.etree.ElementTree as ET

ADDON = pathlib.Path(__file__).resolve().parents[1]
ROOT = ADDON.parent
parser = argparse.ArgumentParser()
parser.add_argument('--odoo-root', type=pathlib.Path)
args = parser.parse_args()

for path in ADDON.rglob('*.py'):
    ast.parse(path.read_text(), filename=str(path))
for path in ADDON.rglob('*.xml'):
    ET.parse(path)
manifest = ast.literal_eval((ADDON / '__manifest__.py').read_text())
assert manifest['version'].startswith('19.0.')
assert 'account_accountant' in manifest['depends']
for path in manifest['data']:
    assert (ADDON / path).is_file(), path
print('Python/XML syntax, manifest, Enterprise dependency, and declared files: PASS', flush=True)

if args.odoo_root:
    sys.path.insert(0, str(args.odoo_root.resolve()))
    from odoo.tools import config
    import odoo.modules.module
    import odoo.release
    config['addons_path'] = str(args.odoo_root.resolve() / 'addons') + ',' + str(ROOT)
    odoo.modules.module.initialize_sys_path()
    import odoo.addons.spx_paybridge_scotia
    prefix = 'odoo.addons.spx_paybridge_scotia'
    print('Actual Odoo import:', odoo.release.version, flush=True)
    test_files = ['test_gateway', 'test_http', 'test_templates']
else:
    prefix = 'spx_paybridge_scotia'
    package = types.ModuleType(prefix)
    package.__path__ = [str(ADDON)]
    sys.modules[prefix] = package
    test_files = ['test_gateway']

suite = unittest.TestSuite()
for name in test_files:
    spec = importlib.util.spec_from_file_location(prefix + '.tests.' + name, ADDON / 'tests' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
