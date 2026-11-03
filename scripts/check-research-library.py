#!/usr/bin/env python3
"""Offline, stdlib-only provenance/index/design-contract gate. No upstream execution."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

REPOSITORY = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


class Gate:
    def __init__(self, library: Path, strict_current: bool) -> None:
        self.library = library.resolve()
        self.strict_current = strict_current
        self.errors: list[str] = []
        self.sources: dict[str, dict] = {}
        self.counts: Counter = Counter()
        self.drift: list[str] = []
        self.failures: list[dict] = []
        self.unknown_rights: list[str] = []
        self.tables: dict[str, dict] = {}
        self.models: dict[tuple[str, str], dict] = {}
        self.current: dict[str, dict] = {}
        self.baseline_data: dict[str, bytes] = {}

    def require(self, condition: object, message: str) -> bool:
        if not condition:
            self.errors.append(message)
        return bool(condition)

    def local(self, root: Path, value: str) -> Path:
        if not isinstance(value, str) or not value:
            raise ValueError("missing artifact path")
        path = (root / value).resolve()
        if Path(value).is_absolute() or not path.is_relative_to(root.resolve()):
            raise ValueError(f"unsafe relative path: {value}")
        return path

    def read_json(self, path: Path) -> object:
        def unique(pairs: list[tuple[str, object]]) -> dict:
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate JSON key {key}")
                result[key] = value
            return result

        return json.loads(path.read_text(), object_pairs_hook=unique)

    def digest(self, data: bytes, expected: str, label: str) -> None:
        self.require(bool(HEX64.fullmatch(str(expected))), f"{label}: invalid sha256")
        self.require(hashlib.sha256(data).hexdigest() == expected, f"{label}: sha256 mismatch")

    def external(self, system: str, manifest_name: str) -> dict:
        root = self.library / system
        manifest = self.read_json(root / manifest_name)
        assert isinstance(manifest, dict)
        records = manifest["sources"]
        self.require(isinstance(records, list) and records, f"{system}: empty sources")
        for record in records:
            label = f"{system}:{record.get('id', '?')}"
            try:
                for key in ("id", "url", "retrieved_date", "version", "purpose", "license"):
                    self.require(bool(record.get(key)), f"{label}: missing {key}")
                self.require(label not in self.sources, f"{label}: duplicate source id")
                self.sources[label] = record
                url = urlparse(record["url"])
                self.require(
                    url.scheme == "https" and bool(url.netloc), f"{label}: non-HTTPS source"
                )
                self.require(
                    bool(DATE.fullmatch(record["retrieved_date"])), f"{label}: invalid date"
                )
                # Unversioned documentation and release metadata are declared separately.
                if system == "ojs" or record.get("kind") == "code":
                    self.require(
                        bool(HEX40.fullmatch(str(record["commit"]))), f"{label}: no fixed commit"
                    )
                    self.require(
                        record["commit"] in record["url"], f"{label}: source URL not commit pinned"
                    )
                path = self.local(root, record["local_artifact"])
                data = path.read_bytes()
                if "original_file_sha256" in record:
                    self.require(
                        bool(HEX64.fullmatch(str(record["original_file_sha256"]))),
                        f"{label}: invalid declared original hash",
                    )
                    self.counts["original_hashes_declared_only"] += 1
                if path.suffix == ".json":
                    self.read_json(path)
                self.digest(data, record["sha256"], label)
                rights = record["license"]
                if record.get("artifact_kind") == "researcher_paraphrase":
                    self.require(
                        record["id"].startswith("pkp-docs:"),
                        f"{label}: unknown-rights source is not declared guide paraphrase",
                    )
                    self.require(
                        "not independently resolved" in rights,
                        f"{label}: undeclared unknown rights",
                    )
                    self.require(
                        bool(HEX64.fullmatch(str(record.get("source_content_sha256")))),
                        f"{label}: missing original hash",
                    )
                    self.require(
                        record["source_content_sha256"] != record["sha256"],
                        f"{label}: paraphrase duplicates original hash",
                    )
                    self.require(path.suffix == ".md", f"{label}: unexpected paraphrase format")
                    self.unknown_rights.append(label)
                elif system == "ojs":
                    self.require("GPL v3" in rights, f"{label}: unrecognized source rights")
                elif record.get("kind") == "code":
                    self.require(rights == "AGPL-3.0", f"{label}: missing declared AGPL rights")
                elif record.get("kind") == "documentation":
                    header = data.decode("utf-8")[:1200]
                    self.require(rights == "CC-BY-4.0", f"{label}: missing CC BY rights")
                    self.require(
                        all(
                            s in header
                            for s in (
                                "Source: " + record["url"],
                                "License: CC BY 4.0",
                                "Open Library of Humanities",
                            )
                        ),
                        f"{label}: missing attribution/URL/license",
                    )
                elif record.get("kind") == "metadata":
                    self.require(
                        rights == "public release metadata",
                        f"{label}: missing metadata declaration",
                    )
                else:
                    self.require(False, f"{label}: unrecognized rights/kind")
                self.counts[f"{system}_sources"] += 1
            except (KeyError, TypeError, ValueError, OSError) as exc:
                self.errors.append(f"{label}: {exc}")
        for failure in manifest.get("collection_failures", []):
            self.require(
                isinstance(failure, dict) and bool(failure),
                f"{system}: malformed retrieval failure",
            )
            self.failures.append({"system": system, **failure})
        return manifest

    def license_evidence(self) -> None:
        for relative, phrase in (
            ("ojs/sources/ojs/docs/COPYING", "GNU GENERAL PUBLIC LICENSE"),
            ("ojs/sources/pkp-lib/LICENSE", "GNU GENERAL PUBLIC LICENSE"),
            ("janeway/sources/LICENSE", "GNU AFFERO GENERAL PUBLIC LICENSE"),
        ):
            self.require(
                phrase in (self.library / relative).read_text(), f"{relative}: missing license text"
            )

    def baseline(self) -> dict:
        manifest = self.read_json(self.library / "current-system/manifest.json")
        assert isinstance(manifest, dict)
        revision = manifest["baseline_commit"]
        if not self.require(
            bool(HEX40.fullmatch(revision)), "current-system: invalid baseline commit"
        ):
            return manifest
        for source in manifest["sources"]:
            relative = source["path"]
            path = self.local(REPOSITORY, relative)
            label = f"current-system:{relative}"
            self.require(label not in self.sources, f"{label}: duplicate source")
            self.sources[label] = source
            result = subprocess.run(
                ["git", "show", f"{revision}:{relative}"],
                cwd=REPOSITORY,
                capture_output=True,
                check=False,
            )
            if self.require(result.returncode == 0, f"{label}: baseline unavailable in local git"):
                self.baseline_data[relative] = result.stdout
                self.digest(result.stdout, source["sha256"], label)
                self.require(
                    len(result.stdout) == source["bytes"], f"{label}: baseline byte count mismatch"
                )
            if (
                not path.exists()
                or hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]
            ):
                self.drift.append(relative)
                if self.strict_current:
                    self.errors.append(
                        f"{label}: worktree changed; baseline refresh required in strict mode"
                    )
            self.counts["baseline_sources"] += 1
        return manifest

    def indexes(self) -> None:
        inventory = self.read_json(self.library / "ojs/schema-inventory.json")
        for table in inventory["tables"]:
            name = table["table"]
            self.require(name not in self.tables, f"ojs: duplicate indexed table {name}")
            self.tables[name] = table
            self.require(f"ojs:{table['source']}" in self.sources, f"ojs.{name}: missing source")
            fields = [f["column"] for f in table["fields"]]
            self.require(len(fields) == len(set(fields)), f"ojs.{name}: duplicate fields")
            source = self.sources.get(f"ojs:{table['source']}")
            if source:
                lines = (
                    self.local(self.library / "ojs", source["local_artifact"])
                    .read_text()
                    .splitlines()
                )
                for item in (
                    *table["fields"],
                    *table["foreign_keys_declared_inside_create"],
                    *table["indexes_declared_inside_create"],
                ):
                    line = item["source_line"]
                    self.require(
                        0 < line <= len(lines)
                        and " ".join(" ".join(lines[line - 1 : line + 79]).split()).startswith(
                            " ".join(item["definition"].split())
                        ),
                        f"ojs.{name}: index/source declaration mismatch at {line}",
                    )
            self.counts["ojs_fields"] += len(fields)
        models = self.read_json(self.library / "janeway/model-fields.json")
        expected_csv = Counter()
        for model in models:
            key = (model["app"], model["model"])
            self.require(key not in self.models, f"janeway: duplicate indexed class {key}")
            self.models[key] = model
            self.require(
                any(
                    s.get("url", "").endswith("/" + model["source"])
                    for k, s in self.sources.items()
                    if k.startswith("janeway:")
                ),
                f"janeway.{key}: missing source path",
            )
            snapshots = [
                self.local(self.library / "janeway", source["local_artifact"]).read_text()
                for key, source in self.sources.items()
                if key.startswith("janeway:")
                and source.get("url", "").endswith("/" + model["source"])
                and "model-fields.txt" in source.get("local_artifact", "")
            ]
            self.require(
                any(
                    f"# upstream class line {model['source_line']}\nclass {model['model']}(" in text
                    for text in snapshots
                ),
                f"janeway.{key}: class/index line mismatch",
            )
            for field in model["fields"]:
                pattern = (
                    rf"# upstream line {field['source_line']}\n\s+{re.escape(field['name'])}\s*="
                )
                self.require(
                    any(re.search(pattern, text) for text in snapshots),
                    f"janeway.{key}.{field['name']}: field/index line mismatch",
                )
                expected_csv[
                    (
                        model["app"],
                        model["model"],
                        field["name"],
                        model["source"],
                        str(field["source_line"]),
                    )
                ] += 1
        with (self.library / "janeway/field-index.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        actual_csv = Counter(
            (r["app"], r["model"], r["field"], r["source_path"], r["line"]) for r in rows
        )
        self.require(actual_csv == expected_csv, "janeway: CSV and JSON field index mismatch")
        self.counts["janeway_fields"] = len(rows)
        current = self.read_json(self.library / "current-system/inventory.json")
        for model in current["tables"]:
            self.require(
                model["class"] not in self.current, f"baseline: duplicate class {model['class']}"
            )
            self.current[model["class"]] = model
            if model["source"] in self.baseline_data:
                tree = ast.parse(self.baseline_data[model["source"]])
                cls = next(
                    (
                        n
                        for n in tree.body
                        if isinstance(n, ast.ClassDef) and n.name == model["class"]
                    ),
                    None,
                )
                self.require(
                    cls is not None and cls.lineno == model["line"],
                    f"baseline.{model['class']}: class/index location mismatch",
                )
                if cls is not None:
                    declared = {
                        n.target.id: n.lineno
                        for n in cls.body
                        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
                    }
                    for field in model["fields"]:
                        self.require(
                            declared.get(field["name"]) == field["line"],
                            f"baseline.{model['class']}.{field['name']}: field/index mismatch",
                        )
            self.require(
                f"current-system:{model['source']}" in self.sources,
                f"baseline.{model['class']}: missing source",
            )
        self.counts.update(
            ojs_tables=len(self.tables),
            janeway_models=len(self.models),
            baseline_tables=len(self.current),
        )

    def reference(self, ref: dict, label: str) -> None:
        key = f"{ref['system']}:{ref['source_id']}"
        self.require(key in self.sources, f"{label}: missing cited source {key}")
        kind = ref.get("entity_type")
        if kind == "source":
            return
        if ref["system"] == "ojs" and kind == "table":
            entity = self.tables.get(ref["entity"])
            if self.require(entity is not None, f"{label}: unknown table {ref['entity']}"):
                self.require(
                    entity["source"] == ref["source_id"], f"{label}: table in different source"
                )
                fields = {f["column"] for f in entity["fields"]}
            else:
                return
        elif ref["system"] == "janeway" and kind == "class":
            entity = self.models.get((ref["app"], ref["entity"]))
            if not self.require(
                entity is not None, f"{label}: unknown Janeway class {ref['entity']}"
            ):
                return
            fields = {f["name"] for f in entity["fields"]}
            self.require(
                self.sources[key]["url"].endswith("/" + entity["source"]),
                f"{label}: class/source mismatch",
            )
            self.require(
                ref.get("upstream_path") == entity["source"]
                and ref.get("upstream_line") == entity["source_line"],
                f"{label}: indexed location mismatch",
            )
        elif ref["system"] == "current-system" and kind == "class":
            entity = self.current.get(ref["entity"])
            if not self.require(
                entity is not None, f"{label}: unknown baseline class {ref['entity']}"
            ):
                return
            self.require(
                entity["source"] == ref["source_id"], f"{label}: baseline class/source mismatch"
            )
            fields = {f["name"] for f in entity["fields"]}
        else:
            self.require(False, f"{label}: unsupported reference shape")
            return
        self.require(
            set(ref.get("fields", [])) <= fields,
            f"{label}: unknown cited fields {set(ref.get('fields', [])) - fields}",
        )
        self.counts["field_references"] += len(ref.get("fields", []))

    def migration_definition(self, revision: str) -> dict:
        """Read our Alembic AST only; never import migrations or application modules."""
        self.require(bool(re.fullmatch(r"[A-Za-z0-9_]+", revision)), "invalid bound revision")
        definitions = []
        for path in (REPOSITORY / "infrastructure/migrations/versions").glob("*.py"):
            tree = ast.parse(path.read_text())
            assignments = {
                target.id: node.value.value
                for node in tree.body
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if assignments.get("revision") == revision:
                definitions.append((path, tree, assignments))
        if len(definitions) != 1:
            raise ValueError(f"revision {revision}: expected exactly one local declaration")
        path, tree, assignments = definitions[0]
        columns: dict[str, set[str]] = {}
        constraints: dict[str, set[str]] = {}

        def literal(node):
            return (
                node.value
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
                else None
            )

        for function in tree.body:
            if not isinstance(function, ast.FunctionDef) or function.name == "downgrade":
                continue
            for call in ast.walk(function):
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                    continue
                operation = call.func.attr
                if operation == "create_table" and call.args and (table := literal(call.args[0])):
                    for child in call.args[1:]:
                        if not isinstance(child, ast.Call):
                            continue
                        if (
                            isinstance(child.func, ast.Attribute)
                            and child.func.attr == "Column"
                            and child.args
                            and (name := literal(child.args[0]))
                        ):
                            columns.setdefault(table, set()).add(name)
                        for keyword in child.keywords:
                            if keyword.arg == "name" and (name := literal(keyword.value)):
                                constraints.setdefault(table, set()).add(name)
                elif (
                    operation == "add_column"
                    and len(call.args) > 1
                    and (table := literal(call.args[0]))
                ):
                    child = call.args[1]
                    if (
                        isinstance(child, ast.Call)
                        and child.args
                        and (name := literal(child.args[0]))
                    ):
                        columns.setdefault(table, set()).add(name)
                elif (
                    operation
                    in {
                        "create_index",
                        "create_foreign_key",
                        "create_unique_constraint",
                        "create_check_constraint",
                    }
                    and len(call.args) > 1
                ):
                    name, table = literal(call.args[0]), literal(call.args[1])
                    if name and table:
                        constraints.setdefault(table, set()).add(name)
        return {
            "path": path,
            "tree": tree,
            "assignments": assignments,
            "columns": columns,
            "constraints": constraints,
        }

    def extension_contracts(self, mapping: dict, models: list[dict]) -> None:
        by_name = {model["class"]: model for model in models}
        for contract in mapping.get("additional_contracts", []):
            text = self.local(REPOSITORY, contract["path"]).read_text()
            declared = dict(re.findall(r"\*\*(\w+) / (publishing_\w+)\*\*", text))
            self.require(
                declared == contract["new_models"], "extension contract: new-model coverage drift"
            )
            revision = contract["migration_id"]
            for name, table in declared.items():
                model = by_name.get(name)
                if self.require(model is not None, f"extension contract: unmapped {name}"):
                    self.require(
                        model["table"] == table
                        and model["migration_id"] == revision
                        and model["contract_source"] == contract["path"],
                        f"{name}: extension table/revision mismatch",
                    )
                    self.require(
                        model.get("field_revision_bindings")
                        == {field: revision for field in model["our_fields"]},
                        f"{name}: extension fields missing exact revision mapping",
                    )
            for name, fields in contract["extended_fields"].items():
                section = re.search(
                    rf"\*\*{re.escape(name)}\*\*:(.*?)(?=\n\n\*\*|\n\n##|\Z)", text, re.S
                )
                self.require(section is not None, f"{name}: missing extension contract section")
                if section:
                    declared_fields = set(re.findall(r"\breview_[a-z_]+_id\b", section.group(1)))
                    self.require(
                        declared_fields == set(fields), f"{name}: extension field coverage drift"
                    )
                model = by_name.get(name)
                if self.require(model is not None, f"extension contract: unmapped relation {name}"):
                    self.require(
                        all(
                            model.get("field_revision_bindings", {}).get(field) == revision
                            for field in fields
                        ),
                        f"{name}: missing altered-field revision binding",
                    )
            for name, required in contract["extended_constraints"].items():
                model = by_name.get(name)
                if self.require(
                    model is not None, f"extension contract: unmapped constraint relation {name}"
                ):
                    bound = {
                        constraint
                        for item in model.get("constraint_revision_bindings", [])
                        if item["revision"] == revision
                        for constraint in item["names"]
                    }
                    self.require(
                        set(required) <= bound,
                        f"{name}: missing altered-constraint revision binding",
                    )
            self.counts["additional_contracts_checked"] += 1
        for binding in mapping.get("implementation_helper_bindings", []):
            tree = ast.parse(self.local(REPOSITORY, binding["path"]).read_text())
            function = next(
                (
                    node
                    for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == binding["name"]
                ),
                None,
            )
            self.require(
                function is not None
                and function.lineno == binding["line"]
                and ast.unparse(function) == binding["declaration"],
                f"implementation FK helper drift: {binding['name']}",
            )
            self.counts["implementation_fk_helpers_bound"] += 1
        for evidence in mapping.get("migration_evidence", []):
            definition = self.migration_definition(evidence["revision"])
            path = self.local(REPOSITORY, evidence["path"])
            self.require(path == definition["path"], "migration evidence: wrong source path")
            self.digest(path.read_bytes(), evidence["sha256"], f"migration:{evidence['revision']}")
            self.require(
                definition["assignments"].get("down_revision") == evidence["down_revision"],
                "migration evidence: wrong predecessor revision",
            )
            sql = path.read_text()
            for name in evidence["sql_functions"]:
                self.require(
                    bool(re.search(rf"CREATE FUNCTION {re.escape(name)}\(", sql)),
                    f"migration evidence: missing SQL function {name}",
                )
            for name in evidence["deferred_triggers"]:
                self.require(
                    bool(
                        re.search(
                            rf"CREATE CONSTRAINT TRIGGER {re.escape(name)}\b[^;]*DEFERRABLE INITIALLY DEFERRED",
                            sql,
                            re.S,
                        )
                    ),
                    f"migration evidence: missing deferred guard {name}",
                )
            self.counts["pinned_implementation_migrations"] += 1

    def design(self) -> None:
        mapping = self.read_json(self.library / "comparison/source-to-implementation.json")
        self.require(
            mapping["source_manifests"]
            == {
                "ojs": "ojs/source-manifest.json",
                "janeway": "janeway/manifest.json",
                "current-system": "current-system/manifest.json",
            },
            "design: unexpected manifest binding",
        )
        self.require(
            mapping["indexes"]
            == {
                "ojs": "ojs/schema-inventory.json",
                "janeway": "janeway/model-fields.json",
                "janeway_csv": "janeway/field-index.csv",
                "current-system": "current-system/inventory.json",
            },
            "design: unexpected index binding",
        )
        contract = self.local(REPOSITORY, mapping["data_contract"]).read_text()
        expected = {"Manuscript", *re.findall(r"^### (\w+) /", contract, re.M)}
        foundation = mapping["models"]
        extensions = mapping.get("extension_models", [])
        foundation_names = [m["class"] for m in foundation]
        extension_names = {m["class"] for m in extensions}
        self.require(
            set(foundation_names) == expected - extension_names
            and len(foundation_names) == len(set(foundation_names)) == 14,
            "design: expected existing Manuscript + 13 foundation contract classes",
        )
        models = [*foundation, *extensions]
        names = [m["class"] for m in models]
        self.extension_contracts(mapping, models)
        self.require(len(names) == len(set(names)), "design: duplicate foundation/extension class")
        for model in extensions:
            source = self.local(REPOSITORY, model["contract_source"]).read_text()
            self.require(
                bool(re.search(rf"\b{re.escape(model['class'])}\b", source)),
                f"{model['class']}: extension absent from cited contract",
            )
        for model in models:
            label = model["class"]
            groups = model["field_groups"]
            fields = [f for g in groups for f in g["our_fields"]]
            self.require(
                fields == model["our_fields"] and len(fields) == len(set(fields)),
                f"{label}: duplicate or inconsistent field groups",
            )
            self.require(
                model["constraints"] and model["intended_acceptance"],
                f"{label}: missing constraint/acceptance",
            )
            self.reference(model["current_baseline"], label)
            covered = set()
            for group in groups:
                self.require(
                    group["origin"] in ("adapted_pattern", "project_governance")
                    and group["adaptation"],
                    f"{label}: unspecified adaptation/origin",
                )
                if revision := group.get("migration_id"):
                    self.require(
                        all(
                            model.get("field_revision_bindings", {}).get(field) == revision
                            for field in group["our_fields"]
                        ),
                        f"{label}: field group/revision binding mismatch",
                    )
                for ref in group["source_refs"]:
                    covered.add(ref["system"])
                    self.reference(ref, label)
            self.require(
                {"ojs", "janeway"} <= covered, f"{label}: incomplete cross-source coverage"
            )
            migration = model.get("migration_id")
            if migration is not None:
                self.require(
                    bool(re.fullmatch(r"[A-Za-z0-9_]+", migration)),
                    f"{label}: invalid migration id",
                )
                files = list((REPOSITORY / "infrastructure/migrations/versions").glob("*.py"))
                self.require(
                    any(
                        re.search(
                            rf"^revision(?:\s*:\s*[^=]+)?\s*=\s*['\"]{re.escape(migration)}['\"]",
                            p.read_text(),
                            re.M,
                        )
                        for p in files
                    ),
                    f"{label}: migration revision not found",
                )
            if model["implementation_status"] == "implemented":
                tree = ast.parse(self.local(REPOSITORY, model["module"]).read_text())
                cls = next(
                    (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == label), None
                )
                self.require(cls is not None, f"{label}: implemented class not found")
                if cls is not None:
                    binding = model["source_binding"]
                    actual_fields = [
                        {
                            "name": n.target.id,
                            "line": n.lineno,
                            "annotation": ast.unparse(n.annotation),
                            "declaration": ast.unparse(n.value),
                        }
                        for n in cls.body
                        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
                    ]
                    self.require(
                        binding["path"] == model["module"] and binding["class_line"] == cls.lineno,
                        f"{label}: implementation class location drift",
                    )
                    self.require(
                        binding["fields"] == actual_fields,
                        f"{label}: implementation field/declaration drift",
                    )
                    self.require(
                        set(model["our_fields"]) == {f["name"] for f in actual_fields},
                        f"{label}: implementation fields not fully mapped",
                    )
                    table_args = next(
                        (
                            n
                            for n in cls.body
                            if isinstance(n, ast.Assign)
                            and any(
                                isinstance(t, ast.Name) and t.id == "__table_args__"
                                for t in n.targets
                            )
                        ),
                        None,
                    )
                    actual_args = (
                        None
                        if table_args is None
                        else {
                            "line": table_args.lineno,
                            "declaration": ast.unparse(table_args.value),
                        }
                    )
                    self.require(
                        binding.get("table_args") == actual_args,
                        f"{label}: implementation constraint declaration drift",
                    )
                    for field, revision in model.get("field_revision_bindings", {}).items():
                        definition = self.migration_definition(revision)
                        self.require(
                            field in definition["columns"].get(model["table"], set()),
                            f"{label}.{field}: bound revision does not create/add field",
                        )
                        self.counts["revision_bound_fields"] += 1
                    source_literals = (
                        {
                            n.value
                            for n in ast.walk(table_args)
                            if isinstance(n, ast.Constant) and isinstance(n.value, str)
                        }
                        if table_args
                        else set()
                    )
                    for item in model.get("constraint_revision_bindings", []):
                        definition = self.migration_definition(item["revision"])
                        for name in item["names"]:
                            self.require(
                                name in source_literals,
                                f"{label}: constraint {name} absent from model AST",
                            )
                            self.require(
                                name in definition["constraints"].get(model["table"], set()),
                                f"{label}: bound revision does not declare constraint {name}",
                            )
                            self.counts["revision_bound_constraints"] += 1
                    self.counts["implementation_fields_bound"] += len(actual_fields)
            else:
                self.require(
                    model["implementation_status"] == "contract_pending_verification",
                    f"{label}: unknown implementation status",
                )
        decisions = mapping["decisions"]
        self.require(
            len({d["id"] for d in decisions}) == len(decisions), "design: duplicate decision id"
        )
        for decision in decisions:
            self.require(
                set(decision["targets"]) <= set(names), f"{decision['id']}: unknown target model"
            )
            self.require(
                all(
                    decision.get(k)
                    for k in ("adopted", "rejected", "intended_acceptance", "source_refs")
                ),
                f"{decision['id']}: incomplete design decision",
            )
            for ref in decision["source_refs"]:
                self.reference(ref, decision["id"])
        # Local citations must remain navigable. External links are provenance, not fetched.
        document = self.library / "comparison/database-decisions.md"
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text()):
            if "://" not in target and not target.startswith("#"):
                self.require(
                    (document.parent / target.split("#", 1)[0]).is_file(),
                    f"design: missing local citation {target}",
                )
        self.counts.update(
            mapped_models=len(names),
            mapped_fields=sum(len(m["our_fields"]) for m in models),
            foundation_models=len(foundation),
            extension_models=len(extensions),
            design_decisions=len(decisions),
        )

    def run(self) -> dict:
        for label, operation in (
            ("OJS manifest", lambda: self.external("ojs", "source-manifest.json")),
            ("Janeway manifest", lambda: self.external("janeway", "manifest.json")),
            ("license evidence", self.license_evidence),
            ("current-system baseline", self.baseline),
            ("indexes", self.indexes),
            ("design mapping", self.design),
        ):
            try:
                operation()
            except (KeyError, TypeError, ValueError, OSError, AssertionError) as exc:
                self.errors.append(f"{label}: {type(exc).__name__}: {exc}")
        return {
            "ok": not self.errors,
            "mode": "offline_static_evidence_only",
            "counts": dict(self.counts),
            "rights_scope": "declared provenance/preserved notices; not legal clearance",
            "original_hash_scope": "original bytes excluded from local artifacts are declared hashes only; retained artifact bytes always verified",
            "unresolved_rights_paraphrases": self.unknown_rights,
            "failed_retrieval_count": len(self.failures),
            "failed_retrievals": self.failures,
            "baseline_policy": "fixed git baseline hashes verified; worktree changes separately reported",
            "strict_current": self.strict_current,
            "worktree_drift": self.drift,
            "errors": self.errors,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=REPOSITORY / "docs/research/library")
    parser.add_argument(
        "--strict-current",
        action="store_true",
        help="Also reject drift from inspected code baseline",
    )
    args = parser.parse_args()
    result = Gate(args.library, args.strict_current).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
