from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from .utils import canonical_json


class ApprovalIdentityError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApprovalPrincipal:
    principal_id: str
    display_name: str
    role: str


DEMO_REVIEWERS: dict[str, ApprovalPrincipal] = {
    "manager-chen": ApprovalPrincipal(
        principal_id="manager-chen",
        display_name="Chen M.",
        role="Department Manager",
    ),
    "finance-lin": ApprovalPrincipal(
        principal_id="finance-lin",
        display_name="Lin Q.",
        role="Finance Reviewer",
    ),
    "owner-zhou": ApprovalPrincipal(
        principal_id="owner-zhou",
        display_name="Zhou T.",
        role="System Owner",
    ),
    "security-he": ApprovalPrincipal(
        principal_id="security-he",
        display_name="He S.",
        role="Security Reviewer",
    ),
    "operator-wu": ApprovalPrincipal(
        principal_id="operator-wu",
        display_name="Wu R.",
        role="Workflow Operator",
    ),
}


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class ApprovalTokenService:
    """Signs demo approval identities and binds them to one persisted checkpoint.

    The public demo session endpoint is intentionally not a production login. In a real
    AgentTeams deployment, the same claims are derived from SSO/Higress identity instead.
    """

    def __init__(self, secret: str | None = None, ttl_seconds: int = 300):
        configured = secret or os.getenv("POLICYFLOW_APPROVAL_SECRET")
        self.secret = (configured or "policyflow-local-demo-change-me").encode("utf-8")
        self.ttl_seconds = ttl_seconds

    @property
    def mode(self) -> str:
        return "configured-hmac" if os.getenv("POLICYFLOW_APPROVAL_SECRET") else "demo-hmac"

    def reviewers(self) -> list[dict[str, str]]:
        return [
            {
                "reviewer_id": item.principal_id,
                "display_name": item.display_name,
                "role": item.role,
            }
            for item in DEMO_REVIEWERS.values()
        ]

    def issue(
        self,
        *,
        reviewer_id: str,
        run_id: str,
        checkpoint_id: str,
        plan_id: str,
        action: str = "approve",
        arguments_hash: str | None = None,
    ) -> dict[str, Any]:
        principal = DEMO_REVIEWERS.get(reviewer_id)
        if principal is None:
            raise ApprovalIdentityError("unknown demo reviewer")
        now = int(time.time())
        claims = {
            "v": 1,
            "iss": "policyflow-demo-identity",
            "sub": principal.principal_id,
            "name": principal.display_name,
            "role": principal.role,
            "run_id": run_id,
            "checkpoint_id": checkpoint_id,
            "plan_id": plan_id,
            "action": action,
            "iat": now,
            "exp": now + self.ttl_seconds,
        }
        if arguments_hash is not None:
            claims["arguments_hash"] = arguments_hash
        encoded = _b64encode(canonical_json(claims).encode("utf-8"))
        signature = _b64encode(hmac.new(self.secret, encoded.encode("ascii"), hashlib.sha256).digest())
        return {
            "approval_token": f"{encoded}.{signature}",
            "expires_at": claims["exp"],
            "principal": {
                "reviewer_id": principal.principal_id,
                "display_name": principal.display_name,
                "role": principal.role,
            },
            "identity_mode": self.mode,
        }

    def verify(
        self,
        token: str,
        *,
        run_id: str,
        checkpoint_id: str,
        plan_id: str,
        action: str = "approve",
        arguments_hash: str | None = None,
    ) -> ApprovalPrincipal:
        try:
            encoded, provided_signature = token.split(".", 1)
            expected_signature = _b64encode(
                hmac.new(self.secret, encoded.encode("ascii"), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(provided_signature, expected_signature):
                raise ApprovalIdentityError("approval token signature is invalid")
            claims = json.loads(_b64decode(encoded).decode("utf-8"))
        except ApprovalIdentityError:
            raise
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApprovalIdentityError("approval token is malformed") from error

        if claims.get("iss") != "policyflow-demo-identity" or claims.get("v") != 1:
            raise ApprovalIdentityError("approval token issuer is invalid")
        if int(claims.get("exp", 0)) < int(time.time()):
            raise ApprovalIdentityError("approval token has expired")
        expected = {
            "run_id": run_id,
            "checkpoint_id": checkpoint_id,
            "plan_id": plan_id,
            "action": action,
        }
        if arguments_hash is not None:
            expected["arguments_hash"] = arguments_hash
        for key, value in expected.items():
            if claims.get(key) != value:
                raise ApprovalIdentityError(f"approval token is not bound to this {key}")
        principal = DEMO_REVIEWERS.get(str(claims.get("sub")))
        if principal is None:
            raise ApprovalIdentityError("approval principal is unknown")
        if claims.get("name") != principal.display_name or claims.get("role") != principal.role:
            raise ApprovalIdentityError("approval identity claims do not match the server directory")
        return principal
