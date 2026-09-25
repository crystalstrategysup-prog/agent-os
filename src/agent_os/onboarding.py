"""Secret-free Telegram Business onboarding plan."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OnboardingStep:
    step_id: str
    title: str
    user_action: bool


STEPS = (
    OnboardingStep(
        "telegram_account", "Create an account in the official Telegram app", True
    ),
    OnboardingStep("owner_approval", "Request access from the AgentOS owner", True),
    OnboardingStep(
        "string_session", "Authorize a StringSession using Telegram QR", True
    ),
    OnboardingStep(
        "credential_bundle", "Store the approved credential bundle locally", True
    ),
    OnboardingStep(
        "telegram_business", "Connect Telegram Business and its business bot", True
    ),
    OnboardingStep("mcp", "Connect AgentOS to an MCP-compatible client", True),
    OnboardingStep("verify", "Run a harmless end-to-end task", False),
)


def public_plan() -> dict[str, object]:
    return {
        "schema": "agent-os.telegram-onboarding/v1",
        "channel": "telegram",
        "website_required": False,
        "primary_auth": "qr",
        "steps": [
            {"id": step.step_id, "title": step.title, "user_action": step.user_action}
            for step in STEPS
        ],
        "secret_policy": {
            "normal_output_contains_secrets": False,
            "approved_bundle_fields": ["API_ID", "API_HASH", "STRING_SESSION"],
            "bundle_must_be_stored_like_password": True,
        },
    }
