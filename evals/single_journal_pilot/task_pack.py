"""Build a bounded, offline editor pack. Never includes engineering answers."""

import argparse
import hashlib
import json
from pathlib import Path

from evals.single_journal_pilot.validate import DATASET, ROOT, validate_dataset

SELECTION = {
    "clinical": ("CLINICAL-02", "CLINICAL-04"),
    "reproducible": ("REPRODUCIBLE-01", "REPRODUCIBLE-03"),
}
MAX_SOURCE_BYTES = 32 * 1024 * 1024


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_path(root, relative):
    root = Path(root).absolute()
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("unsafe_material_path")
    path = root / relative
    # Reject symlinks even if they currently point back inside the repository.
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("symlink_not_allowed")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("unsafe_material_path")
    return path


def read_source(root, path, expected=None):
    path = safe_path(root, path)
    if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("material_missing_or_too_large")
    raw = path.read_bytes()
    if expected and digest(raw) != expected:
        raise ValueError("material_digest_changed")
    return raw


def prepare_pack(root=ROOT, dataset=DATASET):
    """Return exact output bytes; verify all original corpus evidence first."""
    root, dataset = Path(root), Path(dataset)
    safe_path(root, dataset.absolute().relative_to(root.absolute()))
    manifest_raw = read_source(dataset, "manifest.json")
    manifest = json.loads(manifest_raw)
    # The full validator also reads unselected sources: constrain them before it runs.
    for entry in manifest["upstream_manifests"].values():
        read_source(root, entry["path"], entry["sha256"])
    for source in manifest["sources"]:
        read_source(root, source["path"], source["sha256"])
        read_source(dataset, source["snapshot"], source["snapshot_sha256"])
    validation = validate_dataset(dataset, root)
    if not validation["passed"]:
        raise ValueError("corpus_validation_failed")
    checkpoints_raw = read_source(dataset, "checkpoints.json")
    checkpoints = {c["id"]: c for c in json.loads(checkpoints_raw)}
    sources = {s["id"]: s for s in manifest["sources"]}
    papers = {p["id"]: p for p in manifest["papers"]}
    upstream = json.loads(read_source(root, manifest["upstream_manifests"]["documents"]["path"]))
    files, cards, records, materials = {}, [], [], []
    for source_id, ids in SELECTION.items():
        source = sources[source_id]
        paper = papers[source["paper_id"]]
        original_paper = next(p for p in upstream["papers"] if p["id"] == paper["upstream_id"])
        original_file = next(
            f for f in original_paper["files"] if f["case"] == source["binding"]["case"]
        )
        expected_format = "docx" if source_id == "clinical" else "pdf"
        expected_kind = "author original" if expected_format == "docx" else "publisher original"
        if (
            paper["corpus"] != "documents"
            or source["role"] != "manuscript"
            or original_file["format"] != expected_format
            or original_file["kind"] != expected_kind
            or original_file["sha256"] != source["sha256"]
        ):
            raise ValueError("original_format_binding_required")
        target = f"materials/{source_id}.{expected_format}"
        files[target] = read_source(root, source["path"], source["sha256"])
        materials.append(
            {
                "source_id": source_id,
                "paper_id": paper["id"],
                "title": paper["title"],
                "credit": paper["credit"],
                "source_url": paper["source_url"],
                "license": source["license"],
                "version": source["version"],
                "path": target,
                "sha256": source["sha256"],
                "format": expected_format,
                "kind": expected_kind,
                "conversion": "none; exact original bytes copied",
                "scope": source["scope"],
            }
        )
        cards.append(f"## {paper['title']}\n\n文件：`{target}`\n")
        for identity in ids:
            item = checkpoints[identity]
            if (
                item["task"] != "A"
                or item["split"] != "development"
                or item["paper_id"] != paper["id"]
                or item["input_materials"] != [source_id]
            ):
                raise ValueError("development_task_binding_required")
            # Explicit projection: never copy reference/evidence/limitations/semantic_key.
            records.append(
                {
                    "checkpoint_id": identity,
                    "paper_id": paper["id"],
                    "source_id": source_id,
                    "question": item["question"],
                    "assessment": {
                        "reference_answer": None,
                        "answerability": None,
                        "source_locations": [],
                        "ai_answer": None,
                        "ai_version_id": None,
                        "source_correct": None,
                        "text_support": None,
                        "author_association_correct": None,
                        "serious_errors": [],
                        "usable_after_correction": None,
                        "notes": None,
                    },
                }
            )
            cards.append(f"- {identity}：{item['question']}\n")
    intro = """# 编辑首次试用任务卡

本包包含两份公开许可原件、四个开发集问题。不是盲测，也不是已完成的人评。
原作者署名、来源、许可和版本见 materials.json；原件逐字节复制，未转制。

每位编辑复制一份空白记录，独立填写；不要读取工程参考答案或另一人的记录。
先对原件独立作答和定位，再查看 AI 输出。记录页/段和上下文，不以链接存在代替支持。
AI 回答需在独立人工核对后采用；不要让 AI 填写人评、签名或替代负责人决定。

建议 30 分钟：3 分钟阅读材料和许可；7 分钟独立查证；12 分钟在 Pivot 导入、
核对并保存版本、提问和逐条定位；5 分钟纠错/导出；3 分钟填写体验。
这是时间安排，不是计时结果。包含上传、等待、重试、查证和失败；超时可记录未完成。
初次熟悉材料的这个任务不用于宣称提效；严格比较需另按 protocol.md 使用不同匹配材料。

使用本人账号，每篇新建独立资料；核对作者顺序、机构、通讯关系及全文缺口。
只用这两份公开材料；不得上传保密稿件。Mock 回答需记录为模拟，不计真实模型验收。
邮件继续禁用；关键操作继续由有权负责人独立确认。

"""
    files["TASKS.md"] = (intro + "\n".join(cards)).encode()
    files["materials.json"] = encoded(materials)
    files["editor-record.json"] = encoded(
        {
            "schema": "pilot-first-session-record.v1",
            "status": "not_executed",
            "editor_code": None,
            "editor_identity_verified": False,
            "application_commit": None,
            "model_provider": None,
            "model_id": None,
            "started_at": None,
            "finished_at": None,
            "total_elapsed_seconds": None,
            "interruption_seconds": None,
            "completed": None,
            "willing_to_continue": None,
            "reason": None,
            "items": records,
        }
    )
    files["timing.csv"] = (
        b"editor_code,checkpoint_id,mode,started_at,finished_at,upload_seconds,"
        b"model_wait_seconds,verification_seconds,correction_seconds,retry_seconds,"
        b"export_seconds,total_elapsed_seconds,interruption_seconds,completed,note\n"
    )
    package = {
        "schema": "pilot-first-session-pack.v1",
        "source_manifest_sha256": digest(manifest_raw),
        "source_checkpoints_sha256": digest(checkpoints_raw),
        "selection": SELECTION,
        "reference_judgments_included": False,
        "retained_questions_included": False,
        "human_evaluations": 0,
        "complete_response_letters": 0,
        "task_B_included": False,
        "prior_exposure": manifest["prior_exposure"],
        "files": {name: digest(raw) for name, raw in sorted(files.items())},
    }
    files["pack.json"] = encoded(package)
    files["pack.sha256"] = (digest(files["pack.json"]) + "  pack.json\n").encode()
    return files


def build_pack(output, root=ROOT, dataset=DATASET):
    root = Path(root).absolute()
    output = Path(output).absolute()
    relative = output.relative_to(root / "artifacts")
    if not relative.parts:
        raise ValueError("dedicated_output_directory_required")
    safe_path(root, Path("artifacts") / relative)
    if output.exists():
        raise ValueError("output_exists")
    files = prepare_pack(root, dataset)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive mkdir protects previous packs and human annotations from replacement.
    output.mkdir()
    for name, raw in files.items():
        path = output / name
        path.parent.mkdir(exist_ok=True)
        with path.open("xb") as handle:
            handle.write(raw)
    return {
        "status": "prepared_not_evaluated",
        "files": len(files),
        "pack_sha256": digest(files["pack.json"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory below repository artifacts/"
    )
    args = parser.parse_args()
    try:
        report = build_pack(args.output)
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        print(
            json.dumps({"status": "not_created_or_incomplete", "error": "pack_preparation_failed"})
        )
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
