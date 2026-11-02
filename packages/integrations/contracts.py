"""Reserved external adapters; these are contracts, not working OJS/Janeway clients."""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class ExternalManuscriptRef:
    system: Literal["ojs", "janeway"]
    journal_id: str
    manuscript_id: str


class PublishingAdapter(Protocol):
    def read_metadata(self, ref: ExternalManuscriptRef) -> dict:
        """Retrieve authorized metadata; map to domain commands outside this adapter."""
        ...
