import asyncio
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

HAS_DEPS = importlib.util.find_spec("jwt") is not None and importlib.util.find_spec("fastapi") is not None


@unittest.skipUnless(HAS_DEPS, "PyJWT/FastAPI は deploy requirements 導入後に実行")
class AuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module_path = pathlib.Path(__file__).parents[2] / "deploy" / "plan2" / "rag-api" / "auth.py"
        spec = importlib.util.spec_from_file_location("plan2_auth", module_path)
        cls.auth = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.auth
        spec.loader.exec_module(cls.auth)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = pathlib.Path(self.temp.name) / "groups.json"
        self.config.write_text(json.dumps({
            "groups": ["dept-a", "dept-b"],
            "users": {"alice@example.com": ["dept-a"]},
        }), encoding="utf-8")
        self.env = patch.dict(os.environ, {
            "GROUPS_CONFIG": str(self.config),
            "USER_JWT_SECRET": "test-secret",
            "EVAL_TOKEN": "eval-secret",
        }, clear=False)
        self.env.start()
        self.auth._cache = None

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_resolve_groups_rejects_unknown_user(self):
        with self.assertRaises(self.auth.HTTPException) as raised:
            self.auth.resolve_groups("unknown@example.com")
        self.assertEqual(raised.exception.status_code, 403)

    def test_decode_accepts_required_claims(self):
        import jwt

        token = jwt.encode(
            {"sub": "user-1", "email": "alice@example.com", "iss": "open-webui",
             "exp": 4102444800},
            "test-secret",
            algorithm="HS256",
        )
        claims = self.auth.decode_user_jwt(token)
        self.assertEqual(claims["sub"], "user-1")
    def test_decode_rejects_invalid_jwt(self):
        with self.assertRaises(self.auth.HTTPException) as raised:
            self.auth.decode_user_jwt("not-a-jwt")
        self.assertEqual(raised.exception.status_code, 401)

    def test_eval_token_receives_all_groups(self):
        request = type("Request", (), {"headers": {"Authorization": "Bearer eval-secret"}})()
        principal = asyncio.run(self.auth.require_principal(request))
        self.assertTrue(principal.is_eval)
        self.assertEqual(principal.groups, ["dept-a", "dept-b"])


if __name__ == "__main__":
    unittest.main()
