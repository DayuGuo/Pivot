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
