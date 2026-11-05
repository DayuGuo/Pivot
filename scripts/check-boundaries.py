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
    "work_queue": 1,
    "formal_document_models": 0,
    "formal_document_sources": 2,
    "claim_review_models": 0,
    "evaluation_models": 0,
    "evaluation_sources": 4,
    "evaluation_access": 5,
    "evaluation_protocol": -1,
    "claim_review_sources": 3,
    "claim_review_queries": 1,
    "claim_review_metrics": -1,
    "claim_evaluation_package": 2,
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
    "guidance_rules": 3,
    "revision_compare": 3,
    "revision_sources": 3,
}
route_modules = {
    "formal_documents",
    "dossiers",
    "document_imports",
    "dossier_chat",
    "document_candidates",
    "claim_reviews",
    "claim_evaluation",
    "evaluations",
    "guidance",
}
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

# HTTP endpoints must compose services, never import another endpoint module.
# document_candidates is a model-candidate service (no router), not an endpoint.
http_routes = route_modules - {"document_candidates"}
for module in http_routes:
    source = Path("apps/api/publishing/domain") / f"{module}.py"
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Import):
            names = [item.name for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module] if node.module else [item.name for item in node.names]
        else:
            continue
        if any(name.rsplit(".", 1)[-1] in http_routes for name in names):
            raise SystemExit(f"Forbidden dossier route dependency: {source}")
print("Dossier HTTP routes compose services without importing one another")

# Suggestions and model comparison only produce data, never database authority.
for module in ("guidance_rules", "revision_compare"):
    source = Path("apps/api/publishing/domain") / f"{module}.py"
    for node in ast.walk(ast.parse(source.read_text())):
        names = (
            [item.name for item in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
        if any(
            name.split(".")[0] in {"sqlalchemy", "psycopg", "fastapi", "smtplib"}
            or name.rsplit(".", 1)[-1] in {"core", "models", "db", "security", "chat"}
            for name in names
        ):
            raise SystemExit(f"Comparison/rule module cannot acquire mutation authority: {source}")
print("Guidance and revision comparison remain free of database/action authority")
