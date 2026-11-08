"""Guards de transferencia e integridade; sem acesso ao banco principal."""
import argparse
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from scripts import transfer_database as transfer


class TransferTests(unittest.TestCase):
    def test_inventory_hash_ignores_order_and_json_format(self):
        self.assertEqual(transfer.table_hash(['{"b":2,"a":1}', '{"a":3}']),
                         transfer.table_hash(['{ "a":3 }', '{"a":1, "b":2}']))
        self.assertNotEqual(transfer.table_hash(['{"a":1}']), transfer.table_hash(['{"a":2}']))

    def test_wrong_key_never_starts_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = AESGCM.generate_key(bit_length=256)
            nonce = b"0" * 12
            (root / "package.enc").write_bytes(transfer.MAGIC + nonce + AESGCM(key).encrypt(nonce, b"demo", transfer.MAGIC))
            (root / "wrong.key").write_bytes(AESGCM.generate_key(bit_length=256))
            args = argparse.Namespace(package=str(root / "package.enc"), key_file=str(root / "wrong.key"), instance="test")
            with patch.object(transfer, "run") as run:
                with self.assertRaises(InvalidTag):
                    transfer.restore(args)
                run.assert_not_called()

    def test_instance_rejects_paths_and_default(self):
        for name in ("", "../main", "hunter_db;bad", "C:/main"):
            with self.assertRaises(transfer.TransferError):
                transfer.compose_config(name)

    def test_restore_list_only_skips_public_schema_creation(self):
        listing = b"1; 2615 2200 SCHEMA - public owner\n2; 1259 123 TABLE public usuarios owner\n"
        with patch.object(transfer, "dock", side_effect=[listing, b"", b""]) as dock:
            transfer.restore_dump("isolated", b"fake-dump")
            generated_list = dock.call_args_list[1].args[2]
            self.assertNotIn(b"SCHEMA - public", generated_list)
            self.assertIn(b"TABLE public usuarios", generated_list)
            args = dock.call_args_list[2].args[1]
            self.assertIn("--single-transaction", args)
            self.assertNotIn("--clean", args)


if __name__ == "__main__":
    unittest.main()
