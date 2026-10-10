# Part of ci_ai.

from unittest.mock import patch

from odoo.tests.common import TransactionCase

_DNS_PATCH = 'odoo.addons.ci_ai.providers.http_security._hostname_resolves_to_public_ips'


class CiAiTransactionCase(TransactionCase):
    """TransactionCase with DNS checks stubbed for provider base URL validation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._dns_patcher = patch(_DNS_PATCH, return_value=True)
        cls._dns_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._dns_patcher.stop()
        super().tearDownClass()
