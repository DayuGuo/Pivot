"""Mechanical dependency boundary; the gateway cannot acquire publishing authority."""

import ast
from pathlib import Path

for source in Path("packages/model_gateway").glob("*.py"):
    tree = ast.parse(source.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [item.name for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        if any(name.startswith(("apps.api", "sqlalchemy", "psycopg", "smtplib")) for name in names):
            raise SystemExit(f"Forbidden authority dependency: {source}")
print("Model gateway dependency boundaries passed")

# Private dossiers are a layered modular monolith, not mutually importing routers.
# This is a direct-import constraint, not a replacement for runtime authorization.
ranks = {
    "author_links": -1,
    "dossier_evidence": 1,
    "claim_support": 2,
    "dossier_models": 0,
    "dossier_schemas": 0,
    "dossier_access": 1,
    "pagination": 1,
    "dossier_actions": 2,
    "dossier_queries": 2,
    "document_sources": 2,
    "dossier_views": 3,
}
route_modules = {"dossiers", "document_imports", "dossier_chat", "document_candidates"}
for module, rank in ranks.items():
    source = Path("apps/api/publishing/domain") / f"{module}.py"
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Import):
            names = [item.name for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module] if node.module else [item.name for item in node.names]
        else:
            continue
        for name in names:
            dependency = name.rsplit(".", 1)[-1]
            if dependency in route_modules or (dependency in ranks and ranks[dependency] >= rank):
                raise SystemExit(f"Forbidden dossier layer dependency: {source} -> {name}")
            if module == "dossier_schemas" and name.startswith(
                ("sqlalchemy", "fastapi", "packages.model_gateway")
            ):
                raise SystemExit(f"Dossier schemas must remain independent: {source} -> {name}")
print("Dossier model/schema/access/action/query/view boundaries passed")
