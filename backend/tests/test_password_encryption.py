"""Tests for transparent password field encryption (P-SEC fix).

Verifies the four password-bearing models — ``Asset``, ``Resource``,
``ParentPlatform``, ``AccessSource`` — store the ``password`` column as
AES-256-GCM ciphertext and expose the original plaintext through the
``decrypted_password`` property (getter decrypts, setter encrypts).

Also verifies that the migration encrypt logic is idempotent: re-running
``_encrypt_existing_passwords`` on already-encrypted rows skips them instead
of double-encrypting, which would make the data unrecoverable.

These are pure unit tests (no network, no async DB session) so they run in
any environment — the only external requirement is ``FIELD_ENCRYPTION_KEY``
being installed into ``app.core.config.settings`` via ``_install_test_settings``.
"""
import sys
import types
import unittest

import sqlalchemy as sa


def _install_test_settings() -> None:
    """Install a minimal ``app.core.config.settings`` namespace with FIELD_ENCRYPTION_KEY.

    Mirrors the pattern in ``tests/test_security.py`` so the field-encryption
    module can derive a key without touching the real ``.env``.
    """
    settings_obj = types.SimpleNamespace(
        SECRET_KEY="test-secret-key-for-testing",
        SIP_NONCE_SECRET="test-sip-nonce-secret",
        APP_ENV="test",
        APP_EDITION="oss",
        FIELD_ENCRYPTION_KEY="test-field-encryption-key-0123456789",
        PLUGIN_MARKETPLACE_ENABLED=False,
        PROJECT_NAME="PyGBSentry",
        SIP_REALM="pygbsentry.local",
    )
    existing = sys.modules.get("app.core.config")
    if existing is None:
        m = types.ModuleType("app.core.config")
        m.settings = settings_obj
        sys.modules["app.core.config"] = m
        return
    if not hasattr(existing, "settings") or existing.settings is None:
        existing.settings = settings_obj
        return
    for k, v in settings_obj.__dict__.items():
        if not hasattr(existing.settings, k):
            # Pydantic v2 __setattr__ rejects unknown fields when extra != 'allow'.
            object.__setattr__(existing.settings, k, v)


# (model_class, minimal kwargs to satisfy non-nullable columns)
# These kwargs are enough to instantiate the model in memory without a DB
# session — we only exercise the password property, not persistence.
_MODEL_CASES = [
    ("Asset", "app.models.asset", "Asset", {"gb_id": "34020000001320000001"}),
    ("Resource", "app.models.resource", "Resource", {}),
    ("ParentPlatform", "app.models.platform", "ParentPlatform", {
        "server_gb_id": "34020000002000000099",
        "server_ip": "10.0.0.1",
        "client_gb_id": "34020000002000000098",
    }),
    ("AccessSource", "app.models.access_source", "AccessSource", {
        "name": "src1",
        "protocol": "rtsp",
        "host": "10.0.0.2",
    }),
]


class TestPasswordEncryptionRoundTrip(unittest.IsolatedAsyncioTestCase):
    """Verify the 4 models' ``decrypted_password`` property round-trips correctly."""

    def setUp(self) -> None:
        _install_test_settings()

    async def test_round_trip_all_models(self):
        """Setter encrypts; getter returns original plaintext; column holds ciphertext."""
        from app.core import field_crypto

        plaintext = "my-sip-secret-123"
        for label, module_path, cls_name, kwargs in _MODEL_CASES:
            with self.subTest(model=label):
                mod = __import__(module_path, fromlist=[cls_name])
                model_cls = getattr(mod, cls_name)
                obj = model_cls(**kwargs)
                # Initially no password
                obj.decrypted_password = plaintext

                # 1. The password COLUMN must hold ciphertext, not plaintext
                self.assertIsNotNone(obj.password, f"{label}: password column is None")
                self.assertNotEqual(
                    obj.password, plaintext,
                    f"{label}: password column must not store plaintext",
                )
                # 2. The decrypted_password getter must return the original plaintext
                self.assertEqual(
                    obj.decrypted_password, plaintext,
                    f"{label}: decrypted_password did not round-trip",
                )
                # 3. Direct decrypt_field on the column value also works
                self.assertEqual(
                    field_crypto.decrypt_field(obj.password, purpose="sip_password"),
                    plaintext,
                    f"{label}: column value not a valid sip_password ciphertext",
                )

    async def test_ciphertext_differs_across_instances(self):
        """AES-GCM random nonce => two identical plaintexts produce different ciphertexts."""
        for label, module_path, cls_name, kwargs in _MODEL_CASES:
            with self.subTest(model=label):
                mod = __import__(module_path, fromlist=[cls_name])
                model_cls = getattr(mod, cls_name)
                a = model_cls(**kwargs)
                b = model_cls(**kwargs)
                a.decrypted_password = "same-pwd"
                b.decrypted_password = "same-pwd"
                self.assertNotEqual(
                    a.password, b.password,
                    f"{label}: identical plaintexts must yield different ciphertexts (random nonce)",
                )
                # Both still decrypt to the same plaintext
                self.assertEqual(a.decrypted_password, "same-pwd")
                self.assertEqual(b.decrypted_password, "same-pwd")

    async def test_empty_and_none_password(self):
        """None / empty-string plaintext must store None in the column and return None."""
        for label, module_path, cls_name, kwargs in _MODEL_CASES:
            mod = __import__(module_path, fromlist=[cls_name])
            model_cls = getattr(mod, cls_name)

            with self.subTest(model=label, value="None"):
                obj = model_cls(**kwargs)
                obj.decrypted_password = None
                self.assertIsNone(obj.password)
                self.assertIsNone(obj.decrypted_password)

            with self.subTest(model=label, value="empty"):
                obj = model_cls(**kwargs)
                obj.decrypted_password = ""
                self.assertIsNone(obj.password)
                self.assertIsNone(obj.decrypted_password)

    async def test_overwrite_password(self):
        """Re-assigning decrypted_password replaces the ciphertext (no append/double-encrypt)."""
        from app.models.asset import Asset

        asset = Asset(gb_id="34020000001320000002")
        asset.decrypted_password = "first-pwd"
        first_ct = asset.password
        self.assertEqual(asset.decrypted_password, "first-pwd")

        asset.decrypted_password = "second-pwd"
        self.assertNotEqual(asset.password, first_ct)
        self.assertEqual(asset.decrypted_password, "second-pwd")

    async def test_direct_password_assignment_does_not_double_encrypt(self):
        """Assigning a raw ciphertext to ``password`` then reading ``decrypted_password``
        must decrypt it — not treat it as plaintext and re-encrypt.

        This guards against the TypeDecorator-style double-encryption pitfall:
        if ORM reloads the ciphertext from DB into ``password`` and the session
        flushes, the property must NOT re-encrypt.
        """
        from app.core import field_crypto
        from app.models.asset import Asset

        ct = field_crypto.encrypt_field("raw-secret", purpose="sip_password")
        asset = Asset(gb_id="34020000001320000003")
        # Simulate ORM loading the ciphertext column from DB
        asset.password = ct
        # Reading decrypted_password must return plaintext, not re-encrypt
        self.assertEqual(asset.decrypted_password, "raw-secret")
        # The column value must be unchanged (no re-encryption side effect)
        self.assertEqual(asset.password, ct)


class TestMigrationIdempotency(unittest.TestCase):
    """Verify the migration encrypt logic is idempotent (safe to re-run).

    The migration ``c1d2e3f4a5b6_encrypt_password_fields`` uses
    ``decrypt_field`` as a probe: if the stored value decrypts successfully it
    is treated as already-encrypted (skip); otherwise it is treated as
    plaintext and encrypted. This class exercises that logic against an
    in-memory SQLite database so we test real SQL round-trips, not just the
    Python helpers.
    """

    def setUp(self) -> None:
        _install_test_settings()

    def _run_encrypt_logic(self, bind):
        """Replica of the migration's ``_encrypt_existing_passwords`` core logic.

        We replicate rather than import because the real function depends on
        ``alembic.op.get_bind()`` which is only available inside a migration
        context. The replication is intentionally faithful to the migration
        source so a divergence would be caught in review.
        """
        from app.core.field_crypto import encrypt_field, decrypt_field

        tables = ("assets", "resources", "parent_platforms", "access_sources")
        purpose = "sip_password"
        migrated = 0
        skipped = 0
        for table in tables:
            rows = bind.execute(
                sa.text(f"SELECT id, password FROM {table} WHERE password IS NOT NULL AND password <> ''")
            ).fetchall()
            for rid, pwd in rows:
                if decrypt_field(pwd, purpose=purpose) is not None:
                    skipped += 1
                    continue
                encrypted = encrypt_field(pwd, purpose=purpose)
                bind.execute(
                    sa.text(f"UPDATE {table} SET password = :pw WHERE id = :rid"),
                    {"pw": encrypted, "rid": rid},
                )
                migrated += 1
        return migrated, skipped

    def test_idempotent_on_real_sqlite(self):
        """Insert plaintext -> encrypt -> encrypt again => second run skips all."""
        from app.db.base import Base
        from app.models.asset import Asset  # noqa: F401  (register table)
        from app.models.resource import Resource  # noqa: F401
        from app.models.platform import ParentPlatform  # noqa: F401
        from app.models.access_source import AccessSource  # noqa: F401

        engine = sa.create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)

        with engine.connect() as conn:
            # Seed one plaintext row per table. Each table has different NOT
            # NULL columns, so we provide the minimum required columns per table.
            # columns: (table_name, id, plaintext_password, extra_required_cols_dict)
            seeds = [
                ("assets", "34020000001320000001", "asset-pwd-plain",
                 {"gb_id": "34020000001320000001"}),
                ("resources", "34020000001320000002", "resource-pwd-plain", {}),
                ("parent_platforms", "34020000001320000003", "platform-pwd-plain",
                 {"name": "p1", "server_gb_id": "34020000002000000003",
                  "server_ip": "10.0.0.3", "client_gb_id": "34020000002000000098"}),
                ("access_sources", "34020000001320000004", "access-pwd-plain",
                 {"name": "src1", "protocol": "rtsp", "host": "10.0.0.4"}),
            ]
            for table, rid, pwd, extra in seeds:
                cols = {"id": rid, "password": pwd}
                cols.update(extra)
                col_list = ", ".join(cols.keys())
                param_list = ", ".join(f":{c}" for c in cols.keys())
                conn.execute(
                    sa.text(f"INSERT INTO {table} ({col_list}) VALUES ({param_list})"),
                    cols,
                )
            conn.commit()

            # --- First run: all 4 plaintext rows should be encrypted ---
            migrated1, skipped1 = self._run_encrypt_logic(conn)
            conn.commit()
            self.assertEqual(migrated1, 4, "first run must encrypt all 4 plaintext rows")
            self.assertEqual(skipped1, 0, "first run must skip 0 rows")

            # Verify each column now holds ciphertext (not the plaintext)
            for table, rid, original_plain, _extra in seeds:
                stored = conn.execute(
                    sa.text(f"SELECT password FROM {table} WHERE id = :id"), {"id": rid}
                ).scalar()
                self.assertIsNotNone(stored, f"{table}: password became NULL")
                self.assertNotEqual(
                    stored, original_plain,
                    f"{table}: column still holds plaintext after migration",
                )

            # --- Second run: all 4 rows are already encrypted => skip ---
            migrated2, skipped2 = self._run_encrypt_logic(conn)
            conn.commit()
            self.assertEqual(migrated2, 0, "second run must encrypt 0 rows (idempotent)")
            self.assertEqual(skipped2, 4, "second run must skip all 4 rows")

            # Verify the stored ciphertext is identical after the second run
            # (not re-encrypted / not corrupted)
            for table, rid, original_plain, _extra in seeds:
                stored = conn.execute(
                    sa.text(f"SELECT password FROM {table} WHERE id = :id"), {"id": rid}
                ).scalar()
                from app.core.field_crypto import decrypt_field
                self.assertEqual(
                    decrypt_field(stored, purpose="sip_password"),
                    original_plain,
                    f"{table}: plaintext not recoverable after idempotent re-run",
                )

        engine.dispose()

    def test_mixed_plaintext_and_ciphertext(self):
        """A table with some plaintext and some ciphertext rows: only plaintext encrypted."""
        from app.db.base import Base
        from app.models.asset import Asset  # noqa: F401

        engine = sa.create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)

        from app.core.field_crypto import encrypt_field

        pre_encrypted = encrypt_field("already-encrypted", purpose="sip_password")

        with engine.connect() as conn:
            conn.execute(
                sa.text("INSERT INTO assets (id, gb_id, password) VALUES (:id, :gb, :pw)"),
                {"id": "row-plain", "gb": "34020000001320000010", "pw": "plaintext-pwd"},
            )
            conn.execute(
                sa.text("INSERT INTO assets (id, gb_id, password) VALUES (:id, :gb, :pw)"),
                {"id": "row-encrypted", "gb": "34020000001320000011", "pw": pre_encrypted},
            )
            conn.commit()

            migrated, skipped = self._run_encrypt_logic(conn)
            conn.commit()
            self.assertEqual(migrated, 1, "only the plaintext row should be encrypted")
            self.assertEqual(skipped, 1, "the already-encrypted row should be skipped")

            # Verify both rows decrypt correctly
            plain_stored = conn.execute(
                sa.text("SELECT password FROM assets WHERE id = 'row-plain'")
            ).scalar()
            enc_stored = conn.execute(
                sa.text("SELECT password FROM assets WHERE id = 'row-encrypted'")
            ).scalar()

            from app.core.field_crypto import decrypt_field
            self.assertEqual(decrypt_field(plain_stored, purpose="sip_password"), "plaintext-pwd")
            self.assertEqual(decrypt_field(enc_stored, purpose="sip_password"), "already-encrypted")
            # The pre-encrypted row must be byte-identical (not re-encrypted)
            self.assertEqual(enc_stored, pre_encrypted)

        engine.dispose()

    def test_no_rows_no_error(self):
        """Empty tables: migration completes with migrated=0, skipped=0."""
        from app.db.base import Base
        from app.models.asset import Asset  # noqa: F401

        engine = sa.create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)

        with engine.connect() as conn:
            migrated, skipped = self._run_encrypt_logic(conn)
            self.assertEqual(migrated, 0)
            self.assertEqual(skipped, 0)

        engine.dispose()


class TestSipDigestCompatibility(unittest.TestCase):
    """Verify that the decrypted plaintext is usable for SIP Digest authentication.

    The DigestAuth flow needs the raw password to compute the HA1 hash. This
    test ensures ``decrypted_password`` returns a value that produces the
    correct MD5 digest — i.e. the encryption layer is transparent to Digest.
    """

    def setUp(self) -> None:
        _install_test_settings()

    def test_decrypted_password_matches_digest_input(self):
        """The plaintext from decrypted_password must match what DigestAuth expects."""
        import hashlib

        from app.models.asset import Asset

        raw_password = "device-auth-password-456"
        asset = Asset(gb_id="34020000001320000004")
        asset.decrypted_password = raw_password

        # Simulate SIP Digest HA1 = MD5(username:realm:password)
        username = "34020000001320000004"
        realm = "pygbsentry.local"
        expected_ha1 = hashlib.md5(f"{username}:{realm}:{raw_password}".encode()).hexdigest()

        # The decrypted value must equal raw_password so Digest works
        decrypted = asset.decrypted_password
        self.assertEqual(decrypted, raw_password)
        actual_ha1 = hashlib.md5(f"{username}:{realm}:{decrypted}".encode()).hexdigest()
        self.assertEqual(actual_ha1, expected_ha1, "Digest HA1 must match when using decrypted_password")


if __name__ == "__main__":
    unittest.main()
