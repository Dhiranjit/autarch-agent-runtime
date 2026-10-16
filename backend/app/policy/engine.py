"""Deterministic Policy Engine enforcing safety invariants and provenance."""

from app.core.models import ActionProposal, ExecutionContext, PolicyDecision, RiskLevel


class PolicyEngine:
    """Pure Python deterministic policy evaluator."""

    def __init__(self, allowed_domains: list[str] | None = None, trusted_emails: list[str] | None = None) -> None:
        self.allowed_domains = allowed_domains or []
        self.trusted_emails = trusted_emails or []

    def evaluate(self, proposal: ActionProposal, context: ExecutionContext) -> PolicyDecision:
        """Evaluate an action proposal against safety invariants, risk matrix, and provenance."""
        # Level 0, 1, 2: Internal reads, staging, and mutations are auto-approved
        if proposal.risk_level in (RiskLevel.LEVEL_0, RiskLevel.LEVEL_1, RiskLevel.LEVEL_2):
            return PolicyDecision(
                allowed=True,
                requires_approval=False,
                risk_level=proposal.risk_level,
                reason=f"Risk level {proposal.risk_level.name} is auto-approved.",
            )

        # Level 3: External side-effects require approval and provenance verification
        if proposal.risk_level == RiskLevel.LEVEL_3:
            # Provenance Check for email sending
            if proposal.tool_name == "send_email":
                recipient = proposal.args.get("to", "").strip().lower()
                source_sender = context.source_sender.strip().lower()

                # Check if recipient matches source provenance or explicit allowlist
                matches_provenance = recipient == source_sender
                is_trusted = recipient in self.trusted_emails or any(
                    recipient.endswith(f"@{domain.lower()}") for domain in self.allowed_domains
                )

                if not matches_provenance and not is_trusted:
                    return PolicyDecision(
                        allowed=False,
                        requires_approval=True,
                        risk_level=proposal.risk_level,
                        reason=f"Provenance violation: Recipient '{recipient}' does not match inbound sender '{source_sender}' and is not in allowlist.",
                    )

            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                risk_level=proposal.risk_level,
                reason="External side-effect (Level 3) requires user approval.",
            )

        # Deny-by-default for unknown risk levels
        return PolicyDecision(
            allowed=False,
            requires_approval=True,
            risk_level=proposal.risk_level,
            reason="Unknown risk level denied by default.",
        )

