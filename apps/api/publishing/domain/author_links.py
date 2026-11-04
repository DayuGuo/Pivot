"""Conservative, positional author links. Source attribution never authenticates identity."""

import re
from collections import Counter

FRONT_LIMIT = 14000
STOP = re.compile(
    r"(?im)^\s*(?:abstract|summary|keywords|introduction|methods|references|funding|author contributions?|acknowledg\w*|摘要|关键词|引言|参考文献|作者贡献)\b"
)
FIELD_LABELS = {
    "email",
    "e-mail",
    "orcid",
    "affiliation",
    "affiliations",
    "institution",
    "address",
    "contributions",
    "contribution",
    "邮箱",
    "机构",
    "地址",
    "贡献",
}


def name_key(name):
    return " ".join(name.split()).casefold()


def name_pattern(name):
    return r"\s+".join(re.escape(part) for part in name.split())


def byline_ids(text, name):
    match = re.search(name_pattern(name), text[:FRONT_LIMIT])
    if not match:
        return set()
    after = text[match.end() : match.end() + 45]
    markers = re.match(r"[ \t]*([0-9]{1,2}(?:[ \t]*,[ \t]*[0-9]{1,2})*)(?=[*†‡,; \t\n]|$)", after)
    return set(re.findall(r"[0-9]+", markers[1])) if markers else set()


class AuthorLinks:
    def __init__(self, extraction, names):
        self.text = extraction["text"]
        self.front = self.text[:FRONT_LIMIT]
        self.segments = extraction["segments"]
        self.names = names
        self.counts = Counter(name_key(n) for n in names)
        self.ids = {name: byline_ids(self.front, name) for name in names}
        known = set().union(*self.ids.values()) if names else set()
        markers = list(
            re.finditer(
                r"(?m)(?:^|[\n,])[ \t]*([0-9]{1,2})[ \t]*(?!(?:st|nd|rd|th)\b)(?=[^\W\d_])",
                self.front,
            )
        )
        definitions = {}
        for marker in markers:
            if marker[1] in known and marker[1] not in definitions:
                definitions[marker[1]] = marker
        ordered = sorted(definitions.values(), key=lambda v: v.start())
        self.definitions = {}
        for i, marker in enumerate(ordered):
            end = min(
                ordered[i + 1].start() if i + 1 < len(ordered) else len(self.front),
                marker.end() + 650,
            )
            stop = STOP.search(self.front, marker.end(), end)
            if stop:
                end = stop.start()
            self.definitions[marker[1]] = (marker.start(), end)

    def span(self, start, end):
        while start < end and self.text[start].isspace():
            start += 1
        while end > start and self.text[end - 1].isspace():
            end -= 1
        segment = next(s for s in self.segments if s["start"] <= start < s["end"])
        return {
            "start": start,
            "end": end,
            "quote": self.text[start:end],
            "kind": segment["kind"],
            "number": segment["number"],
        }

    def relation(self, method, spans):
        return {
            "method": method,
            "identity_authenticated": False,
            "evidence": [self.span(*span) for span in spans],
        }

    def named_blocks(self, name):
        pattern = (
            r"(?im)^[ \t]*(?:(?:author(?:[ \t]*\d+)?|作者(?:[ \t]*\d+)?|corresponding[ \t]+author|通讯作者)[ \t]*[:：][ \t]*)?"
            + name_pattern(name)
            + r"(?=[ \t]*[:：(]|[ \t]*$|[ \t]+(?:is|was)[ \t]+(?:in|at|affiliated[ \t]+with)\b)"
        )
        for match in re.finditer(pattern, self.front):
            end = min(len(self.front), match.end() + 1000)
            stop = STOP.search(self.front, match.end(), end)
            if stop:
                end = stop.start()
            tail = self.front[match.end() : end]
            # Every new personal/section heading ends the block, even when the
            # proposing model omitted that person from its author list.
            for heading in re.finditer(r"(?m)^([^:\n]{2,150})[：:]", tail):
                label = re.sub(r"[ \t]*[0-9]+$", "", heading[1].strip().casefold())
                if label not in FIELD_LABELS and not re.search(r"\.[ \t]*e-?mail$", label):
                    end = match.end() + heading.start()
                    break
            for other in self.names:
                if name_key(other) == name_key(name):
                    continue
                found = re.search(name_pattern(other), self.front[match.end() : end])
                if found:
                    end = match.end() + found.start()
            yield match.start(), end

    def email_footnote(self, name, value):
        first_definition = min((a for a, _ in self.definitions.values()), default=0)
        byline = self.front[:first_definition] if first_definition else ""
        marked = re.search(name_pattern(name) + r"[0-9, \t]*\*", byline)
        if marked and byline.count("*") == 1 and self.counts[name_key(name)] == 1:
            found = re.search(
                r"(?im)^\s*\*[ \t]*(?:e-?mail|邮箱)[ \t]*[:：][ \t]*" + re.escape(value), self.front
            )
            if found:
                return [(marked.start(), marked.end()), (found.start(), found.end())]
        return None

    def contact_email(self, name):
        if self.counts[name_key(name)] != 1:
            return None
        addresses = {}
        for start, end in self.named_blocks(name):
            for match in re.finditer(
                r"(?i)(?:e-?mail|邮箱)(?:[ \t]*[0-9]+)?[ \t]*[:：][ \t\n]*([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
                self.front[start:end],
            ):
                addresses[match[1]] = (start, end)
        if len(addresses) == 1:
            address, span = next(iter(addresses.items()))
            return address, self.front[span[0] : span[1]]
        return None

    def bind(self, name, value, kind):
        if self.counts[name_key(name)] != 1:
            return None
        compact = "".join(value.split())
        if kind == "affiliation" and self.ids[name]:
            ids = self.ids[name]
            if ids <= self.definitions.keys():
                for number in sorted(ids):
                    start, end = self.definitions[number]
                    if compact in "".join(self.front[start:end].split()):
                        author = re.search(name_pattern(name) + r"[^\n;]{0,45}", self.front)
                        return self.relation(
                            "byline_marker", [(author.start(), author.end()), (start, end)]
                        )
                return None
        if kind == "email":
            footnote = self.email_footnote(name, value)
            if footnote:
                return self.relation("email_footnote", footnote)
        for start, end in self.named_blocks(name):
            block = self.front[start:end]
            if compact and compact in "".join(block.split()):
                return self.relation("named_block", [(start, end)])
        # A single *isolated* byline plus its bounded front matter is acceptable.
        # A model returning one name from a multi-person byline is not sufficient.
        if len(self.names) == 1:
            match = re.search(r"(?im)^\s*" + name_pattern(name) + r"[ \t]*$", self.front)
            if match:
                end = min(len(self.front), match.end() + 1400)
                stop = STOP.search(self.front, match.end(), end)
                if stop:
                    end = stop.start()
                block = self.front[match.end() : end]
                for heading in re.finditer(r"(?m)^([^:\n]{2,150})[：:]", block):
                    if heading[1].strip().casefold() not in FIELD_LABELS:
                        end = match.end() + heading.start()
                        break
                if compact in "".join(self.front[match.end() : end].split()):
                    return self.relation("single_byline", [(match.start(), end)])
        return None

    def correspondence(self, name):
        if self.counts[name_key(name)] != 1:
            return None
        patterns = [
            r"(?im)(?:corresponding[ \t]+author|通讯作者)[ \t]*[:：][ \t]*"
            + name_pattern(name)
            + r"(?!\w)",
            name_pattern(name) + r"[ \t]*[(:（]?[ \t]*(?:corresponding[ \t]+author|通讯作者)\b",
        ]
        for pattern in patterns:
            found = re.search(pattern, self.front)
            if found:
                return self.relation("named_correspondence", [(found.start(), found.end())])
        return None


def author_issues(data):
    """Current record conflicts, not a claim of identity verification."""
    issues = []
    for field, code in (
        ("name", "duplicate_name"),
        ("orcid", "duplicate_orcid"),
        ("email", "shared_email"),
    ):
        values = [name_key(a.get(field) or "") for a in data.get("authors", [])]
        counts = Counter(v for v in values if v)
        for i, value in enumerate(values):
            if value and counts[value] > 1:
                issues.append({"field_path": f"authors.{i}.{field}", "reason": code})
    return issues
