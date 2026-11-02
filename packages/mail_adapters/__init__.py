"""Read-only mailbox connection probes. No environment, storage, or send operations."""

from .probe import MailCredentials, ProbeConfig, ProbeResult, probe

__all__ = ["MailCredentials", "ProbeConfig", "ProbeResult", "probe"]
