"""Tests for transparent media_node secret field encryption (P0-02 fix).

Verifies the ``MediaNode`` model stores the ``secret`` column as AES-256-GCM
ciphertext (purpose="media_secret") and exposes the original plaintext through
the ``decrypted_secret`` property (getter decrypts, setter encrypts).

Also verifies that the migration encrypt logic is idempotent: re-running
``_encrypt_existing_secrets`` on already-encrypted rows skips them instead
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

    Mirrors the pattern in ``tests/test_password_encryption.py`` so the field-encryption
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
        MEDIA_SERVER_SECRET="test-global-media-secret",
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


# Minimal kwargs to satisfy MediaNode non-nullable columns for in-memory instantiation.
_MIN_KWARGS = {"ip": "10.0.0.1"}


class TestSecretEncryptionRoundTrip(unittest.IsolatedAsyncioTestCase):
    """Verify ``MediaNode.decrypted_secret`` property round-trips correctly."""

    def setUp(self) -> None:
        _install_test_settings()

    async def test_round_trip(self):
        """Setter encrypts; getter returns original plaintext; column holds ciphertext."""
        from app.core import field_crypto
        from app.models.media_node import MediaNode

        plaintext = "my-zlm-api-secret-456"
        node = MediaNode(**_MIN_KWARGS)
        node.decrypted_secret = plaintext

        # 1. The secret COLUMN must hold ciphertext, not plaintext
        self.assertIsNotNone(node.secret, "secret column is None")
        self.assertNotEqual(
            node.secret, plaintext,
            "secret column must not store plaintext",
        )
        # 2. The decrypted_secret getter must return the original plaintext
        self.assertEqual(
            node.decrypted_secret, plaintext,
            "decrypted_secret did not round-trip",
        )
        # 3. Direct decrypt_field on the column value also works (purpose="media_secret")
        self.assertEqual(
            field_crypto.decrypt_field(node.secret, purpose="media_secret"),
            plaintext,
            "column value not a valid media_secret ciphertext",
        )

    async def test_ciphertext_differs_across_instances(self):
        """AES-GCM random nonce => two identical plaintexts produce different ciphertexts."""
        from app.models.media_node import MediaNode

        a = MediaNode(**_MIN_KWARGS)
        b = MediaNode(**_MIN_KWARGS)
        a.decrypted_secret = "same-secret"
        b.decrypted_secret = "same-secret"
        self.assertNotEqual(
            a.secret, b.secret,
            "identical plaintexts must yield different ciphertexts (random nonce)",
        )
        # Both still decrypt to the same plaintext
        self.assertEqual(a.decrypted_secret, "same-secret")
        self.assertEqual(b.decrypted_secret, "same-secret")

    async def test_empty_and_none_secret(self):
        """None / empty-string plaintext must store None in the column and return None."""
        from app.models.media_node import MediaNode

        with self.subTest(value="None"):
            obj = MediaNode(**_MIN_KWARGS)
            obj.decrypted_secret = None
            self.assertIsNone(obj.secret)
            self.assertIsNone(obj.decrypted_secret)

        with self.subTest(value="empty"):
            obj = MediaNode(**_MIN_KWARGS)
            obj.decrypted_secret = ""
            self.assertIsNone(obj.secret)
            self.assertIsNone(obj.decrypted_secret)

    async def test_overwrite_secret(self):
        """Re-assigning decrypted_secret replaces the ciphertext (no append/double-encrypt)."""
        from app.models.media_node import MediaNode

        node = MediaNode(**_MIN_KWARGS)
        node.decrypted_secret = "first-secret"
        first_ct = node.secret
        self.assertEqual(node.decrypted_secret, "first-secret")

        node.decrypted_secret = "second-secret"
        self.assertNotEqual(node.secret, first_ct)
        self.assertEqual(node.decrypted_secret, "second-secret")

    async def test_direct_secret_assignment_does_not_double_encrypt(self):
        """Assigning a raw ciphertext to ``secret`` then reading ``decrypted_secret``
        must decrypt it — not treat it as plaintext and re-encrypt.

        This guards against the TypeDecorator-style double-encryption pitfall:
        if ORM reloads the ciphertext from DB into ``secret`` and the session
        flushes, the property must NOT re-encrypt.
        """
        from app.core import field_crypto
        from app.models.media_node import MediaNode

        ct = field_crypto.encrypt_field("raw-zlm-secret", purpose="media_secret")
        node = MediaNode(**_MIN_KWARGS)
        # Simulate ORM loading the ciphertext column from DB
        node.secret = ct
        # Reading decrypted_secret must return plaintext, not re-encrypt
        self.assertEqual(node.decrypted_secret, "raw-zlm-secret")
        # The column value must be unchanged (no re-encryption side effect)
        self.assertEqual(node.secret, ct)

    async def test_purpose_isolation_from_sip_password(self):
        """media_secret ciphertext must NOT be decryptable with sip_password purpose
        (and vice versa), confirming purpose-based key isolation."""
        from app.core import field_crypto
        from app.models.media_node import MediaNode

        node = MediaNode(**_MIN_KWARGS)
        node.decrypted_secret = "media-secret-value"

        # Decrypting with wrong purpose must fail (return None)
        wrong = field_crypto.decrypt_field(node.secret, purpose="sip_password")
        self.assertIsNone(wrong, "media_secret ciphertext must not decrypt with sip_password purpose")

        # Correct purpose works
        correct = field_crypto.decrypt_field(node.secret, purpose="media_secret")
        self.assertEqual(correct, "media-secret-value")


class TestMigrationIdempotency(unittest.TestCase):
    """Verify the migration encrypt logic is idempotent (safe to re-run).

    The migration ``d1e2f3a4b5c6_encrypt_media_node_secret`` uses
    ``decrypt_field`` as a probe: if the stored value decrypts successfully it
    is treated as already-encrypted (skip); otherwise it is treated as
    plaintext and encrypted. This class exercises that logic against an
    in-memory SQLite database so we test real SQL round-trips.
    """

    def setUp(self) -> None:
        _install_test_settings()

    def _run_encrypt_logic(self, bind):
        """Replica of the migration's ``_encrypt_existing_secrets`` core logic.

        We replicate rather than import because the real function depends on
        ``alembic.op.get_bind()`` which is only available inside a migration
        context. The replication is intentionally faithful to the migration
        source so a divergence would be caught in review.
        """
        from app.core.field_crypto import encrypt_field, decrypt_field

        purpose = "media_secret"
        migrated = 0
        skipped = 0
        rows = bind.execute(
            sa.text("SELECT id, secret FROM media_nodes WHERE secret IS NOT NULL AND secret <> ''")
        ).fetchall()
        for rid, sec in rows:
            if decrypt_field(sec, purpose=purpose) is not None:
                skipped += 1
                continue
            encrypted = encrypt_field(sec, purpose=purpose)
            bind.execute(
                sa.text("UPDATE media_nodes SET secret = :sec WHERE id = :rid"),
                {"sec": encrypted, "rid": rid},
            )
            migrated += 1
        return migrated, skipped

    def _create_engine_with_schema(self):
        """Create in-memory SQLite engine with media_nodes table created."""
        from app.db.base import Base
        from app.models.media_node import MediaNode  # noqa: F401  (register table)

        engine = sa.create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        return engine

    def test_idempotent_on_real_sqlite(self):
        """Insert plaintext -> encrypt -> encrypt again => second run skips all."""
        engine = self._create_engine_with_schema()

        with engine.connect() as conn:
            # Seed plaintext row(s)
            seeds = [
                ("node-1", "10.0.0.1", "plaintext-zlm-secret-1"),
                ("node-2", "10.0.0.2", "plaintext-zlm-secret-2"),
            ]
            for rid, ip, secret_plain in seeds:
                conn.execute(
                    sa.text("INSERT INTO media_nodes (id, ip, secret) VALUES (:id, :ip, :sec)"),
                    {"id": rid, "ip": ip, "sec": secret_plain},
                )
            conn.commit()

            # --- First run: all plaintext rows should be encrypted ---
            migrated1, skipped1 = self._run_encrypt_logic(conn)
            conn.commit()
            self.assertEqual(migrated1, 2, "first run must encrypt all 2 plaintext rows")
            self.assertEqual(skipped1, 0, "first run must skip 0 rows")

            # Verify each column now holds ciphertext (not the plaintext)
            for rid, _ip, original_plain in seeds:
                stored = conn.execute(
                    sa.text("SELECT secret FROM media_nodes WHERE id = :id"), {"id": rid}
                ).scalar()
                self.assertIsNotNone(stored, f"{rid}: secret became NULL")
                self.assertNotEqual(
                    stored, original_plain,
                    f"{rid}: column still holds plaintext after migration",
                )

            # --- Second run: all rows are already encrypted => skip ---
            migrated2, skipped2 = self._run_encrypt_logic(conn)
            conn.commit()
            self.assertEqual(migrated2, 0, "second run must encrypt 0 rows (idempotent)")
            self.assertEqual(skipped2, 2, "second run must skip all 2 rows")

            # Verify the stored ciphertext is identical after the second run
            # (not re-encrypted / not corrupted)
            for rid, _ip, original_plain in seeds:
                stored = conn.execute(
                    sa.text("SELECT secret FROM media_nodes WHERE id = :id"), {"id": rid}
                ).scalar()
                from app.core.field_crypto import decrypt_field
                self.assertEqual(
                    decrypt_field(stored, purpose="media_secret"),
                    original_plain,
                    f"{rid}: plaintext not recoverable after idempotent re-run",
                )

        engine.dispose()

    def test_mixed_plaintext_and_ciphertext(self):
        """A table with some plaintext and some ciphertext rows: only plaintext encrypted."""
        engine = self._create_engine_with_schema()

        from app.core.field_crypto import encrypt_field

        pre_encrypted = encrypt_field("already-encrypted-secret", purpose="media_secret")

        with engine.connect() as conn:
            conn.execute(
                sa.text("INSERT INTO media_nodes (id, ip, secret) VALUES (:id, :ip, :sec)"),
                {"id": "node-plain", "ip": "10.0.0.1", "sec": "plaintext-zlm-secret"},
            )
            conn.execute(
                sa.text("INSERT INTO media_nodes (id, ip, secret) VALUES (:id, :ip, :sec)"),
                {"id": "node-encrypted", "ip": "10.0.0.2", "sec": pre_encrypted},
            )
            conn.commit()

            migrated, skipped = self._run_encrypt_logic(conn)
            conn.commit()
            self.assertEqual(migrated, 1, "only the plaintext row should be encrypted")
            self.assertEqual(skipped, 1, "the already-encrypted row should be skipped")

            # Verify both rows decrypt correctly
            plain_stored = conn.execute(
                sa.text("SELECT secret FROM media_nodes WHERE id = 'node-plain'")
            ).scalar()
            enc_stored = conn.execute(
                sa.text("SELECT secret FROM media_nodes WHERE id = 'node-encrypted'")
            ).scalar()

            from app.core.field_crypto import decrypt_field
            self.assertEqual(decrypt_field(plain_stored, purpose="media_secret"), "plaintext-zlm-secret")
            self.assertEqual(decrypt_field(enc_stored, purpose="media_secret"), "already-encrypted-secret")
            # The pre-encrypted row must be byte-identical (not re-encrypted)
            self.assertEqual(enc_stored, pre_encrypted)

        engine.dispose()

    def test_no_rows_no_error(self):
        """Empty table: migration completes with migrated=0, skipped=0."""
        engine = self._create_engine_with_schema()

        with engine.connect() as conn:
            migrated, skipped = self._run_encrypt_logic(conn)
            self.assertEqual(migrated, 0)
            self.assertEqual(skipped, 0)

        engine.dispose()

    def test_null_secret_skipped(self):
        """Rows with NULL secret are filtered out by WHERE clause (no error)."""
        engine = self._create_engine_with_schema()

        with engine.connect() as conn:
            # secret is NOT NULL in the model, but for this test we bypass ORM
            # and insert via raw SQL with an empty string to verify filtering.
            conn.execute(
                sa.text("INSERT INTO media_nodes (id, ip, secret) VALUES (:id, :ip, :sec)"),
                {"id": "node-empty", "ip": "10.0.0.1", "sec": ""},
            )
            conn.commit()

            migrated, skipped = self._run_encrypt_logic(conn)
            self.assertEqual(migrated, 0, "empty secret should be filtered out")
            self.assertEqual(skipped, 0)

        engine.dispose()


class TestZlmApiCompatibility(unittest.TestCase):
    """Verify that the decrypted plaintext is usable for ZLM API authentication.

    ZLM API calls pass the secret as a ``secret`` query/body parameter. This
    test ensures ``decrypted_secret`` returns the exact plaintext the ZLM
    server expects — i.e. the encryption layer is transparent to ZLM calls.
    """

    def setUp(self) -> None:
        _install_test_settings()

    def test_decrypted_secret_matches_zlm_input(self):
        """The plaintext from decrypted_secret must equal what ZLM expects."""
        from app.models.media_node import MediaNode

        raw_secret = "zlm-api-key-abc-123"
        node = MediaNode(ip="10.0.0.1")
        node.decrypted_secret = raw_secret

        # The decrypted value must equal raw_secret so ZLM API auth works
        decrypted = node.decrypted_secret
        self.assertEqual(decrypted, raw_secret)
        # Simulate what ZLM API client does: pass secret as plain string
        self.assertTrue(decrypted.isascii(), "ZLM secret must be ASCII-safe")


if __name__ == "__main__":
    unittest.main()
