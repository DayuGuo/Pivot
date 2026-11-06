"""Pure quote-to-original mapping; never guesses across omitted source boundaries."""


def original_location(origin, start, end, quote):
    if not origin:
        return None
    if start < 0 or end <= start or end - start != len(quote):
        raise ValueError("original_quote_incomplete")
    first = origin["selection_start"] + start
    last = origin["selection_start"] + end
    parts = []
    covered = [False] * len(quote)
    for segment in origin["segments"]:
        left, right = max(first, segment["start"]), min(last, segment["end"])
        if left < right:
            value = segment["text"][left - segment["start"] : right - segment["start"]]
            if value != quote[left - first : right - first]:
                raise ValueError("original_quote_mismatch")
            parts.append(
                {
                    "kind": segment["kind"],
                    "number": segment["number"],
                    "start": left,
                    "end": right,
                    "quote": value,
                }
            )
            covered[left - first : right - first] = [True] * (right - left)
    gaps = [
        (a["end"], b["start"])
        for a, b in zip(origin["segments"], origin["segments"][1:], strict=False)
    ]
    if not parts or first < origin["selection_start"] or last > origin["selection_end"]:
        raise ValueError("original_quote_incomplete")
    for offset, mapped in enumerate(covered):
        if not mapped and (
            quote[offset] != "\n"
            or not any(a <= first + offset < b and b - a == 2 for a, b in gaps)
        ):
            raise ValueError("original_quote_incomplete")
    return {
        "filename": origin["filename"],
        "sha256": origin["sha256"],
        "download_url": origin["download_url"],
        "locations": parts,
        "scope_start": origin["selection_start"],
        "scope_end": origin["selection_end"],
    }
