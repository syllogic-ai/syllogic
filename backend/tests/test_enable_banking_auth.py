"""Tests for Enable Banking JWT authentication."""

import os
import sys
import unittest
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Generate a test RSA key pair for testing
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

_test_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PRIVATE_KEY_PEM = _test_private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode("utf-8")
TEST_APP_ID = "test-app-id-123"


class TestCreateEbJwt(unittest.TestCase):
    def test_jwt_has_correct_claims(self):
        from app.integrations.enable_banking_auth import create_eb_jwt
        import jwt as pyjwt

        token = create_eb_jwt(TEST_APP_ID, TEST_PRIVATE_KEY_PEM, ttl=3600)
        # Decode without verification to check claims
        decoded = pyjwt.decode(token, options={"verify_signature": False})

        self.assertEqual(decoded["iss"], "enablebanking.com")
        self.assertEqual(decoded["aud"], "api.enablebanking.com")
        self.assertIn("iat", decoded)
        self.assertIn("exp", decoded)
        self.assertAlmostEqual(decoded["exp"] - decoded["iat"], 3600, delta=5)

    def test_jwt_header_fields(self):
        from app.integrations.enable_banking_auth import create_eb_jwt
        import jwt as pyjwt

        token = create_eb_jwt(TEST_APP_ID, TEST_PRIVATE_KEY_PEM)
        header = pyjwt.get_unverified_header(token)

        self.assertEqual(header["typ"], "JWT")
        self.assertEqual(header["alg"], "RS256")
        self.assertEqual(header["kid"], TEST_APP_ID)

    def test_jwt_verifiable_with_public_key(self):
        from app.integrations.enable_banking_auth import create_eb_jwt
        import jwt as pyjwt

        token = create_eb_jwt(TEST_APP_ID, TEST_PRIVATE_KEY_PEM)
        public_key = _test_private_key.public_key()

        decoded = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience="api.enablebanking.com",
            issuer="enablebanking.com",
        )
        self.assertEqual(decoded["iss"], "enablebanking.com")


class TestEbApiClient(unittest.TestCase):
    def test_client_initializes_with_env_vars(self):
        os.environ["ENABLE_BANKING_APP_ID"] = TEST_APP_ID
        os.environ["ENABLE_BANKING_PRIVATE_KEY"] = TEST_PRIVATE_KEY_PEM

        from app.integrations.enable_banking_auth import EnableBankingClient

        client = EnableBankingClient()
        self.assertEqual(client.app_id, TEST_APP_ID)
        self.assertEqual(client.base_url, "https://api.enablebanking.com")

        # Cleanup
        del os.environ["ENABLE_BANKING_APP_ID"]
        del os.environ["ENABLE_BANKING_PRIVATE_KEY"]

    def test_client_get_headers_returns_bearer_jwt(self):
        os.environ["ENABLE_BANKING_APP_ID"] = TEST_APP_ID
        os.environ["ENABLE_BANKING_PRIVATE_KEY"] = TEST_PRIVATE_KEY_PEM

        from app.integrations.enable_banking_auth import EnableBankingClient

        client = EnableBankingClient()
        headers = client.get_headers()
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Bearer "))

        del os.environ["ENABLE_BANKING_APP_ID"]
        del os.environ["ENABLE_BANKING_PRIVATE_KEY"]


if __name__ == "__main__":
    unittest.main()
