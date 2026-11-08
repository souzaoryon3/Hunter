"""Caracterizacao das protecoes operacionais, sem acessar principal/cofres."""

import base64
import hashlib
import hmac
import re
import unittest
from unittest.mock import AsyncMock

from ops.broker_permissions import permissions
from ops.security import provision, scram, verify


class SecurityOperationsTests(unittest.IsolatedAsyncioTestCase):
    def test_scram_verifier_matches_password_without_plaintext(self):
        password = "synthetic-only-test-password"
        verifier = scram(password)
        self.assertNotIn(password, verifier)
        _, params, keys = verifier.split("$")
        rounds, salt = params.split(":")
        stored, server = keys.split(":")
        salted = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(salt), int(rounds)
        )
        self.assertEqual(
            base64.b64decode(stored),
            hashlib.sha256(hmac.digest(salted, b"Client Key", "sha256")).digest(),
        )
        self.assertEqual(
            base64.b64decode(server), hmac.digest(salted, b"Server Key", "sha256")
        )
        self.assertNotEqual(verifier, scram(password))

    def test_broker_acl_default_exchange_and_scope(self):
        acl = permissions()
        self.assertTrue(re.fullmatch(acl["write"], "amq.default"))
        for operation in ("configure", "read", "write"):
            self.assertTrue(re.fullmatch(acl[operation], "hunter.price"))
            self.assertTrue(re.fullmatch(acl[operation], "hunter.price.dead"))
            self.assertFalse(re.fullmatch(acl[operation], "other.price"))
        self.assertFalse(re.fullmatch(acl["configure"], "amq.default"))

    async def test_provision_wrong_destination_has_no_mutations(self):
        c = AsyncMock()
        c.fetchval.return_value = "projeto1"
        with self.assertRaises(ValueError):
            await provision(
                c,
                expected_database="hunter_db",
                app_password="test",
                migration_password="test",
            )
        c.execute.assert_not_awaited()

    async def test_provision_rejects_existing_login(self):
        c = AsyncMock()
        c.fetchval.side_effect = ["hunter_sim", True]
        with self.assertRaises(ValueError):
            await provision(
                c,
                expected_database="hunter_sim",
                app_password="test",
                migration_password="test",
            )
        c.execute.assert_not_awaited()

    async def test_runtime_checks_all_dangerous_flags(self):
        base = dict(
            name="hunter_app",
            rolsuper=False,
            rolcreatedb=False,
            rolcreaterole=False,
            rolreplication=False,
            rolbypassrls=False,
        )
        for flag in [k for k in base if k != "name"]:
            c = AsyncMock()
            c.fetchrow.return_value = {**base, flag: True}
            with self.assertRaises(ValueError):
                await verify(c)
        c = AsyncMock()
        c.fetchrow.return_value = base
        c.fetchval.return_value = False
        self.assertEqual((await verify(c))["name"], "hunter_app")

    async def test_runtime_rejects_schema_history_and_ownership_privileges(self):
        base = dict(
            name="hunter_app",
            rolsuper=False,
            rolcreatedb=False,
            rolcreaterole=False,
            rolreplication=False,
            rolbypassrls=False,
        )
        for replies in ([True], [False, True], [False] * 7 + [1]):
            c = AsyncMock()
            c.fetchrow.return_value = base
            c.fetchval.side_effect = replies
            with self.assertRaises(ValueError):
                await verify(c)
