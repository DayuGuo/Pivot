"""Read-only Janeway source collection. Never import or execute upstream code."""

import ast
import hashlib
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = Path("/tmp/publishing-janeway-research/upstream")
REV = "e24b23bd112ff7ca08097620d8a31041a25f9d26"
DATE = "2026-11-02"
SOURCES = ROOT / "sources"
SOURCES.mkdir(exist_ok=True)
manifest = []


def save(name, data, url, purpose, kind="code", upstream_bytes=None):
    path = SOURCES / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode() if isinstance(data, str) else data
    path.write_bytes(raw)
    record = {
        "id": name,
        "url": url,
        "retrieved_date": DATE,
        "version": "v1.8.4" if kind == "code" else "live documentation",
        "commit": REV if kind == "code" else None,
        "local_artifact": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "purpose": purpose,
        "kind": kind,
        "license": "AGPL-3.0"
        if kind == "code"
        else "CC-BY-4.0"
        if kind == "documentation"
        else "public release metadata",
    }
    if upstream_bytes is not None:
        record["original_file_sha256"] = hashlib.sha256(upstream_bytes).hexdigest()
    manifest.append(record)


models = {
    "submission": [
        "Article",
        "FrozenAuthor",
        "CreditRecord",
        "ArticleFunding",
        "ArticleStageLog",
        "Keyword",
        "KeywordArticle",
        "Section",
        "Licence",
        "Field",
        "FieldAnswer",
        "SubmissionConfiguration",
    ],
    "review": [
        "EditorAssignment",
        "ReviewRound",
        "ReviewAssignment",
        "ReviewForm",
        "BaseReviewFormElement",
        "ReviewFormElement",
        "ReviewAssignmentAnswer",
        "ReviewAssignmentAnswerFile",
        "FrozenReviewFormElement",
        "RevisionAction",
        "RevisionRequest",
        "DecisionDraft",
        "EditorOverride",
    ],
    "core": [
        "Account",
        "Role",
        "AccountRole",
        "File",
        "FileHistory",
        "Galley",
        "Task",
        "TaskCompleteEvents",
        "Workflow",
        "WorkflowElement",
        "WorkflowLog",
        "ControlledAffiliation",
    ],
    "journal": [
        "Journal",
        "Issue",
        "IssueType",
        "IssueGalley",
        "IssueEditor",
        "ArticleOrdering",
        "PrePublicationChecklistItem",
        "FixedPubCheckItems",
        "PresetPublicationCheckItem",
    ],
    "copyediting": ["CopyeditAssignment", "AuthorReview"],
    "typesetting": [
        "TypesettingClaim",
        "TypesettingRound",
        "TypesettingAssignment",
        "GalleyProofing",
        "TypesettingCorrection",
    ],
    "identifiers": ["Identifier", "BrokenDOI"],
    "production": ["ProductionAssignment", "TypesetTask"],
    "proofing": ["ProofingAssignment", "ProofingRound", "ProofingTask", "TypesetterProofingTask"],
}
inventory = []
for app, names in models.items():
    source_path = f"src/{app}/models.py"
    source_bytes = (CACHE / source_path).read_bytes()
    source = source_bytes.decode()
    tree = ast.parse(source)
    snippets = [
        f"# Janeway v1.8.4 / {REV}\n# {source_path}\n# Copyright Birkbeck, University of London; AGPL v3. See LICENSE.\n# Static excerpts: field declarations and Meta only; upstream code was NOT executed.\n"
    ]
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in names:
            continue
        fields, metas, chunks = [], {}, []
        for child in node.body:
            value = child.value if isinstance(child, (ast.Assign, ast.AnnAssign)) else None
            if isinstance(value, ast.Call):
                callname = ast.unparse(value.func)
                if callname.endswith(("Field", "ForeignKey", "OneToOneField", "ManyToManyField")):
                    target = child.targets[0] if isinstance(child, ast.Assign) else child.target
                    keywords = {k.arg: ast.unparse(k.value) for k in value.keywords if k.arg}
                    fields.append(
                        {
                            "name": ast.unparse(target),
                            "field_type": callname,
                            "arguments": [ast.unparse(arg) for arg in value.args],
                            "options": keywords,
                            "source_line": child.lineno,
                        }
                    )
                    chunks.append(
                        f"    # upstream line {child.lineno}\n"
                        + "\n".join(
                            "    " + line
                            for line in ast.get_source_segment(source, child).splitlines()
                        )
                    )
            if isinstance(child, ast.ClassDef) and child.name == "Meta":
                chunks.append(
                    "\n".join(
                        "    " + line for line in ast.get_source_segment(source, child).splitlines()
                    )
                )
                for part in child.body:
                    if isinstance(part, ast.Assign):
                        metas[ast.unparse(part.targets[0])] = ast.unparse(part.value)
        inventory.append(
            {
                "app": app,
                "model": node.name,
                "source": source_path,
                "source_line": node.lineno,
                "bases": [ast.unparse(b) for b in node.bases],
                "fields": fields,
                "declared_meta": metas,
                "limitations": "AST local declarations only; inherited fields, generated translations, implicit id/FK indexes and migration operations are not resolved.",
            }
        )
        snippets.append(
            f"\n# upstream class line {node.lineno}\nclass {node.name}("
            + ",".join(ast.unparse(b) for b in node.bases)
            + "):\n"
            + "\n".join(chunks)
            + "\n"
        )
    save(
        f"{app}-model-fields.txt",
        "\n".join(snippets),
        f"https://github.com/openlibhums/janeway/blob/{REV}/{source_path}",
        f"{app} model fields, explicit relationships and declared constraints",
        upstream_bytes=source_bytes,
    )

(ROOT / "model-fields.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")

for path, chosen in {
    "src/security/decorators.py": [
        "editor_is_not_author",
        "user_can_edit_article",
        "reviewer_user_for_assignment_required",
        "file_user_required",
        "file_history_user_required",
    ],
    "src/security/logic.py": ["can_see_pii", "can_view_file", "can_view_file_history"],
    "src/submission/models.py": ["Article"],
}.items():
    source = (CACHE / path).read_text()
    tree = ast.parse(source)
    parts = [
        f"# Static security/workflow excerpts from {path}\n# Janeway {REV}; AGPL v3; see LICENSE.\n"
    ]
    if chosen == ["Article"]:
        article = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Article")
        for node in article.body:
            if isinstance(node, ast.FunctionDef) and node.name in {
                "save",
                "accept_article",
                "decline_article",
                "can_edit",
                "user_is_author",
            }:
                parts.append(
                    f"# upstream line {node.lineno}\n" + ast.get_source_segment(source, node)
                )
    else:
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in chosen:
                parts.append(
                    f"# upstream line {node.lineno}\n" + ast.get_source_segment(source, node)
                )
    save(
        path.replace("/", "-") + ".txt",
        "\n\n".join(parts),
        f"https://github.com/openlibhums/janeway/blob/{REV}/{path}",
        "security, ownership, anonymity or transition implementation excerpts",
        upstream_bytes=(CACHE / path).read_bytes(),
    )

migration_paths = [
    "src/review/migrations/0001_initial.py",
    "src/review/migrations/0011_keep_answers_on_form_delete.py",
    "src/review/migrations/0025_reviewassignmentanswerfile.py",
    "src/submission/migrations/0057_frozen_email_and_orcid.py",
    "src/submission/migrations/0079_frozen_author_null_to_string.py",
    "src/submission/migrations/0084_remove_frozenauthor_country_and_more.py",
    "src/submission/migrations/0085_creditrecord_and_more.py",
    "src/submission/migrations/0088_auto_20250506_1214.py",
    "src/typesetting/migrations/0002_typesettinground.py",
    "src/typesetting/migrations/0018_selected_files.py",
    "src/journal/migrations/0059_alter_prepublicationchecklistitem_completed_by.py",
]
for path in migration_paths:
    local = CACHE / path
    if local.exists():
        save(
            "migrations/" + path.replace("/", "-") + ".txt",
            local.read_bytes(),
            f"https://github.com/openlibhums/janeway/blob/{REV}/{path}",
            "historical schema/backfill and immutable evidence lessons",
        )

save(
    "LICENSE",
    (CACHE / "LICENSE").read_bytes(),
    f"https://github.com/openlibhums/janeway/blob/{REV}/LICENSE",
    "upstream source license",
)
metadata = json.loads(Path("/tmp/publishing-janeway-research/releases.json").read_text())
release = next(r for r in metadata if r["tag_name"] == "v1.8.4")
small = {
    key: release[key]
    for key in ["tag_name", "name", "published_at", "prerelease", "draft", "html_url", "body"]
}
small.update(commit=REV, canonical_repository="openlibhums/janeway")
save(
    "release-v1.8.4.json",
    json.dumps(small, indent=2),
    release["html_url"],
    "stable version and security fixes",
    "metadata",
)

pages = {
    "about": "https://janeway.systems/pages/support/about/index.html",
    "editor-workflow": "https://janeway.systems/pages/support/guides/editor-guide-overview",
    "author-guide": "https://janeway.systems/pages/support/guides/author-guide",
    "editor-review": "https://janeway.systems/pages/support/guides/editor-guide-to-review",
    "draft-decisions": "https://janeway.systems/pages/support/guides/editor-guide-to-draft-decisions",
    "copyediting": "https://janeway.systems/pages/support/guides/editor-guide-to-copyediting",
    "typesetting": "https://janeway.systems/pages/support/guides/editor-guide-to-typesetting",
    "pre-publication": "https://janeway.systems/pages/support/guides/editor-guide-to-prepub",
    "review-overview": "https://janeway.systems/pages/support/review/index.html",
    "journal-setup": "https://janeway.systems/pages/support/guides/journal-setup",
}


class MainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.active = True
        if self.active and tag in {"h1", "h2", "h3", "h4", "p", "li", "br", "div", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "main":
            self.active = False
        if self.active and tag in {"h1", "h2", "h3", "h4", "p", "li", "div", "section"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


for name, url in pages.items():
    req = urllib.request.Request(url, headers={"User-Agent": "Publishing-OS-public-research"})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        final_url = response.url
    html = raw.decode()
    assert "creativecommons.org/licenses/by/4.0/" in html and 'rel="license"' in html
    parser = MainText()
    parser.feed(html)
    content = "\n".join(
        re.sub(r"\s+", " ", line).strip() for line in "".join(parser.parts).splitlines()
    )
    content = re.sub(r"\n{3,}", "\n\n", content)
    attribution = f"Janeway official documentation — Birkbeck, University of London / Open Library of Humanities\nSource: {final_url}\nRetrieved: {DATE}\nLicense: CC BY 4.0 — http://creativecommons.org/licenses/by/4.0/\nHTML main-text extraction; navigation, images and formatting omitted. Content wording unmodified.\nVersion: current unversioned website; NOT asserted to be v1.8.4-specific.\n\n"
    save(
        "docs/" + name + ".txt",
        attribution + content,
        final_url,
        "licensed official operator workflow/privacy/metadata main text",
        "documentation",
        upstream_bytes=raw,
    )
    (SOURCES / "docs" / f"{name}.html").unlink(missing_ok=True)

(ROOT / "manifest.json").write_text(
    json.dumps(
        {
            "project": "Janeway",
            "canonical_repository": "https://github.com/openlibhums/janeway",
            "stable_tag": "v1.8.4",
            "commit": REV,
            "retrieved_date": DATE,
            "executed_upstream_code": False,
            "documentation_version_warning": "Current unversioned official pages are recorded by bytes/hash; code observations use v1.8.4 only.",
            "sources": manifest,
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n"
)
print(
    json.dumps(
        {
            "source_count": len(manifest),
            "model_count": len(inventory),
            "field_count": sum(len(m["fields"]) for m in inventory),
        }
    )
)
