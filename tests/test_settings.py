"""Validacao sem rede: destino errado e recusado ANTES de conectar."""

import os
import unittest
from unittest.mock import patch

from config.settings import (
    APISettings,
    database_url,
    require_test_database,
    test_database_url,
    cors_origins,
    jwt_secret,
)
from messaging.config import Settings
from messaging.testing import require_isolated
from unittest.mock import AsyncMock


class ConfigurationTests(unittest.TestCase):
    def test_signed_jwt_without_expiration_is_rejected(self):
        from backend.security import get_current_user, SECRET_KEY, ALGORITHM
        from jose import jwt
        from fastapi import HTTPException

        with self.assertRaises(HTTPException):
            get_current_user(jwt.encode({"sub": "7"}, SECRET_KEY, algorithm=ALGORITHM))

    def test_database_is_explicit_and_errors_hide_values(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            database_url()
        for value in (
            " ",
            "not-a-url",
            "postgresql://u:private@host/db?host=other",
            "postgresql://u:private@host/db?database=hunter_db",
            "postgresql://u:private@host/db#fragment",
        ):
            with patch.dict(os.environ, {"DATABASE_URL": value}, clear=True):
                with self.assertRaises(ValueError) as error:
                    database_url()
                self.assertNotIn("private", str(error.exception))

    def test_main_and_disguised_databases_are_rejected(self):
        for value in (
            "postgresql://hunter_test@localhost:5432/hunter_db",
            "postgresql://hunter_test@localhost:55432/hunter_db",
            "postgresql://postgres@localhost:55432/hunter_test",
            "postgresql://hunter_test@remote:55432/hunter_test",
            "postgresql://hunter_test@localhost:55432/hunter_test?dbname=hunter_db",
            "postgresql://hunter_test@localhost:55432/hunter_test?hostaddr=remote",
        ):
            with (
                patch.dict(os.environ, {"HUNTER_QUEUE_TESTS": "1"}, clear=True),
                self.assertRaises(ValueError),
            ):
                require_test_database(value)

    def test_isolated_destination_requires_opt_in(self):
        value = "postgresql://hunter_test@localhost:55432/hunter_test"
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            require_test_database(value)
        with patch.dict(os.environ, {"HUNTER_QUEUE_TESTS": "1"}, clear=True):
            self.assertEqual(require_test_database(value), value)

    def test_mixed_test_environment_is_rejected(self):
        with (
            patch.dict(
                os.environ,
                {
                    "HUNTER_QUEUE_TESTS": "1",
                    "HUNTER_TEST_DATABASE_URL": "postgresql://hunter_test@localhost:55432/hunter_test",
                    "DATABASE_URL": "postgresql://postgres@localhost:5432/hunter_db",
                },
                clear=True,
            ),
            self.assertRaises(ValueError),
        ):
            test_database_url()

    def test_migration_connection_is_separate_and_mandatory(self):
        with (
            patch.dict(
                os.environ, {"DATABASE_URL": "postgresql://app@host/db"}, clear=True
            ),
            self.assertRaises(ValueError),
        ):
            database_url(migration=True)
        from scripts.catalog_stage2 import main_admin_dsn

        with (
            patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgresql://app@localhost:5432/hunter_db",
                    "MIGRATION_DATABASE_URL": "postgresql://owner@localhost:5432/other_db",
                },
                clear=True,
            ),
            self.assertRaises(ValueError),
        ):
            main_admin_dsn(os.environ["DATABASE_URL"])

    def test_settings_do_not_print_connection_secrets(self):
        self.assertNotIn("private", repr(Settings("private", "private")))
        self.assertNotIn("private", repr(APISettings("private")))

    def test_pool_bounds_and_production_security(self):
        values = dict(
            JWT_SECRET_KEY="0123456789abcdef" * 4,
            DATABASE_URL="postgresql://app@host/db?sslmode=verify-full",
            HUNTER_ENV="production",
            CORS_ORIGINS="https://hunter.example",
        )
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(APISettings.load().pool_max, 10)
            self.assertEqual(cors_origins(), ("https://hunter.example",))
            with (
                patch.dict(os.environ, {"DB_POOL_MIN": "11", "DB_POOL_MAX": "10"}),
                self.assertRaises(ValueError),
            ):
                APISettings.load()
            with (
                patch.dict(os.environ, {"JWT_SECRET_KEY": "weak"}),
                self.assertRaises(ValueError),
            ):
                jwt_secret()
            for placeholder in (
                "x" * 64,
                "REPLACE_WITH_RANDOM_SECRET_AT_LEAST_32_CHARACTERS",
            ):
                with (
                    patch.dict(os.environ, {"JWT_SECRET_KEY": placeholder}),
                    self.assertRaises(ValueError),
                ):
                    jwt_secret()
            with (
                patch.dict(os.environ, {"CORS_ORIGINS": "*"}),
                self.assertRaises(ValueError),
            ):
                cors_origins()

    def test_queue_guard_rejects_main_even_with_test_broker(self):
        with (
            patch.dict(os.environ, {"HUNTER_QUEUE_TESTS": "1"}, clear=True),
            self.assertRaises(ValueError),
        ):
            require_isolated(
                Settings(
                    "postgresql://postgres@localhost:5432/hunter_db",
                    "amqp://localhost:5673/hunter_test",
                    prefix="hunter_test",
                )
            )


class RuntimeRoleTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_refuses_privileged_role_without_changing_it(self):
        from config.settings import assert_runtime_role

        conn = AsyncMock()
        conn.fetchrow.return_value = {
            "rolsuper": True,
            "rolcreatedb": False,
            "rolcreaterole": False,
        }
        with (
            patch.dict(os.environ, {"HUNTER_ENV": "production"}),
            self.assertRaises(ValueError),
        ):
            await assert_runtime_role(conn)
        conn.execute.assert_not_called()

    async def test_local_preserves_existing_role(self):
        from config.settings import assert_runtime_role

        conn = AsyncMock()
        with patch.dict(os.environ, {"HUNTER_ENV": "local"}):
            await assert_runtime_role(conn)
        conn.fetchrow.assert_not_called()
