"""Private-dossier inputs and deterministic completeness, independent of DB and HTTP."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field

from .schemas import AuthorInput, Keyword, StrictInput, _email_format_valid


class DossierAuthor(AuthorInput):
    source_note: str = Field(default="", max_length=1000)


class DossierData(StrictInput):
    title: str = Field(default="", max_length=500)
    abstract: str = Field(default="", max_length=12000)
    language: Literal["zh", "en"] = "zh"
    keywords: list[Keyword] = Field(default_factory=list, max_length=12)
    authors: list[DossierAuthor] = Field(default_factory=list, max_length=20)
    source_kind: Literal["synthetic", "public_authorized"]
    source_note: str = Field(min_length=5, max_length=2000)


def require_explicit_true(value):
    if value is not True:
        raise ValueError("需要负责人显式确认，必须为布尔true")
    return value


ExplicitTrue = Annotated[Literal[True], BeforeValidator(require_explicit_true)]

RequestID = Annotated[UUID, Field(strict=False)]


class CreateInput(StrictInput):
    request_id: RequestID
    title: str = Field(default="", max_length=500)
    source_kind: Literal["synthetic", "public_authorized"]
    source_note: str = Field(min_length=5, max_length=2000)
    authorized_material: ExplicitTrue


class TextUpload(StrictInput):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=4, max_length=1398104)


class SaveInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=1)
    data: DossierData
    file: TextUpload | None = None


class ConfirmInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=1)
    version_id: RequestID
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    acknowledged: ExplicitTrue


class AssistInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=1)
    version_id: RequestID
    message: str = Field(min_length=1, max_length=2000)


def missing(data: DossierData, has_file: bool) -> list[dict]:
    found = []

    def need(ok, field, message):
        if not ok:
            found.append({"field": field, "message": message})

    need(len(data.title) >= 3, "title", "题名至少3个字符")
    need(len(data.abstract) >= 40, "abstract", "摘要至少40个字符")
    need(any(word.strip() for word in data.keywords), "keywords", "至少填写1个关键词")
    need(has_file, "file", "请上传完整TXT或Markdown正文")
    need(bool(data.authors), "authors", "至少填写1位作者")
    need(
        sum(a.corresponding for a in data.authors) == 1,
        "authors.corresponding",
        "请选择且仅选择1位通讯作者",
    )
    for index, author in enumerate(data.authors):
        need(bool(author.name), f"authors.{index}.name", "请填写作者姓名")
        need(
            bool(author.affiliations) and all(a.strip() for a in author.affiliations),
            f"authors.{index}.affiliations",
            "请填写作者机构",
        )
        need(bool(author.source_note), f"authors.{index}.source_note", "请说明作者资料的提供来源")
        if author.corresponding:
            need(
                _email_format_valid(author.email),
                f"authors.{index}.email",
                "请填写有效的通讯邮箱；格式检查不是身份认证",
            )
    return found
