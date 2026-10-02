"""Synthetic OIDC provider installed only by the disposable browser harness."""

import base64
import hashlib
import html
import os
import secrets
import time
from urllib.parse import parse_qs, urlencode

from authlib.jose import JsonWebKey, jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse


def install_provider(harness, base_url: str) -> None:
    issuer = base_url + "/__test/oidc"
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public_key = JsonWebKey.import_key(private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo), {"kid": "browser-harness"}).as_dict()
    transactions: dict[str, dict[str, str]] = {}
    codes: dict[str, dict[str, str]] = {}

    @harness.get("/__test/oidc/.well-known/openid-configuration")
    def discovery():
        return {"issuer": issuer, "authorization_endpoint": issuer + "/authorize", "token_endpoint": issuer + "/token", "jwks_uri": issuer + "/jwks", "response_types_supported": ["code"], "subject_types_supported": ["public"], "id_token_signing_alg_values_supported": ["RS256"], "code_challenge_methods_supported": ["S256"], "token_endpoint_auth_methods_supported": ["client_secret_basic"]}

    @harness.get("/__test/oidc/jwks")
    def jwks():
        return {"keys": [public_key]}

    @harness.get("/__test/oidc/authorize")
    def authorize(request: Request):
        values = dict(request.query_params)
        if values.get("client_id") != os.environ["OIDC_CLIENT_ID"] or values.get("redirect_uri") != os.environ["OIDC_REDIRECT_URI"] or values.get("response_type") != "code" or values.get("code_challenge_method") != "S256":
            raise HTTPException(400, "Invalid provider authorization")
        transaction = secrets.token_urlsafe(24)
        transactions[transaction] = values
        choices = [("student-a", "Student A"), ("student-b", "Student B"), ("administrator", "Administrator"), ("new-student", "Invited new student")]
        links = "".join(f'<p><a href="{issuer}/grant?transaction={html.escape(transaction)}&subject={subject}">{label}</a></p>' for subject, label in choices)
        return HTMLResponse('<h1>Browser harness identity provider</h1><p>Test provider. No real credentials.</p>' + links)

    @harness.get("/__test/oidc/grant")
    def grant(transaction: str, subject: str):
        values = transactions.pop(transaction, None)
        if values is None or subject not in {"student-a", "student-b", "administrator", "new-student"}:
            raise HTTPException(400, "Invalid provider transaction")
        code = secrets.token_urlsafe(32)
        codes[code] = {**values, "subject": subject}
        return RedirectResponse(values["redirect_uri"] + "?" + urlencode({"state": values["state"], "code": code}), status_code=302)

    @harness.post("/__test/oidc/token")
    async def token(request: Request):
        authorization = base64.b64encode((os.environ["OIDC_CLIENT_ID"] + ":" + os.environ["OIDC_CLIENT_SECRET"]).encode()).decode()
        if request.headers.get("authorization") != "Basic " + authorization:
            raise HTTPException(401, "Invalid provider client")
        values = {key: value[0] for key, value in parse_qs((await request.body()).decode()).items()}
        code = codes.pop(values.get("code", ""), None)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(values.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode()
        if code is None or values.get("redirect_uri") != code["redirect_uri"] or challenge != code["code_challenge"]:
            raise HTTPException(400, "Invalid provider code or PKCE")
        subject = code["subject"]
        email = {"student-a": "a@example.test", "student-b": "b@example.test", "administrator": "admin@example.test", "new-student": "new.student@example.test"}[subject]
        claims = {"iss": issuer, "sub": subject, "aud": os.environ["OIDC_CLIENT_ID"], "iat": int(time.time()), "exp": int(time.time()) + 300, "nonce": code["nonce"], "email": email, "email_verified": True, "name": subject.replace("-", " ").title()}
        identity = jwt.encode({"alg": "RS256", "kid": "browser-harness"}, claims, pem).decode()
        return {"access_token": secrets.token_urlsafe(24), "token_type": "Bearer", "expires_in": 300, "id_token": identity}
