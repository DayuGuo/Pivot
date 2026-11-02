"""Bounded intake DTOs. Draft completeness and human declarations stay server-owned."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Keyword = Annotated[str, Field(max_length=80)]
Affiliation = Annotated[str, Field(max_length=500)]
Contribution = Annotated[str, Field(max_length=100)]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class AuthorInput(StrictInput):
    name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=254)
    orcid: str | None = Field(default=None, max_length=64)
    affiliations: list[Affiliation] = Field(default_factory=list, max_length=20)
    corresponding: bool = False
    contributions: list[Contribution] = Field(default_factory=list, max_length=20)

    @field_validator("orcid", mode="before")
    @classmethod
    def normalized_orcid(cls, value):
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("ORCID必须为文本格式")
        value = value.strip()
        if not value:
            return None
        match = re.fullmatch(
            r"(?:https?://(?:www\.)?orcid\.org/)?([0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9Xx])/?",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            raise ValueError("ORCID格式应为0000-0000-0000-0000；格式检查不代表身份已核实")
        return match.group(1).upper()


class DeclarationsInput(StrictInput):
    originality: bool = False
    copyright: bool = False
    competing_interests: Literal["unanswered", "none", "declared"] = "unanswered"
    competing_interests_text: str = Field(default="", max_length=4000)
    ethics: Literal["unanswered", "not_applicable", "approved"] = "unanswered"
    ethics_reference: str = Field(default="", max_length=1000)


class IntakeData(StrictInput):
    title: str = Field(default="", max_length=500)
    abstract: str = Field(default="", max_length=12000)
    language: Literal["zh", "en"] = "zh"
    article_type: Literal["research_article"] = "research_article"
    keywords: list[Keyword] = Field(default_factory=list, max_length=12)
    authors: list[AuthorInput] = Field(default_factory=list, max_length=20)
    declarations: DeclarationsInput = Field(default_factory=DeclarationsInput)
    funding_statement: str = Field(default="", max_length=4000)


class IntakeCandidates(StrictInput):
    """AI may propose metadata; it cannot supply declarations, identity grants or authority."""

    title: str | None = Field(default=None, max_length=500)
    abstract: str | None = Field(default=None, max_length=12000)
    language: Literal["zh", "en"] | None = None
    article_type: Literal["research_article"] | None = None
    keywords: list[Keyword] | None = Field(default=None, max_length=12)
    authors: list[AuthorInput] | None = Field(default=None, max_length=20)
    funding_statement: str | None = Field(default=None, max_length=4000)


class FileUpload(StrictInput):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=4, max_length=1398104)
    purpose: Literal["manuscript", "blinded_manuscript", "response", "similarity_report", "proof"]


def _email_format_valid(value: str) -> bool:
    """Conservative mailbox syntax, not delivery/account verification or SMTP access."""
    if not value or len(value) > 254 or value.count("@") != 1:
        return False
    local, domain = value.rsplit("@", 1)
    if (
        not local
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
    ):
        return False
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    labels = domain.split(".")
    return (
        len(domain) <= 253
        and len(labels) >= 2
        and all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in labels
        )
    )


def missing_requirements(data: IntakeData, file_purposes: set[str]) -> list[dict[str, str]]:
    """Drafts may remain incomplete; confirmation consumes this deterministic checklist."""
    missing = []

    def require(condition: bool, field: str, message: str):
        if not condition:
            missing.append({"field": field, "message": message})

    require(len(data.title.strip()) >= 3, "title", "标题至少需要3个字符")
    require(len(data.abstract.strip()) >= 40, "abstract", "摘要至少需要40个字符")
    require(any(word.strip() for word in data.keywords), "keywords", "至少填写1个关键词")
    require(bool(data.authors), "authors", "至少填写1位作者")
    for index, author in enumerate(data.authors):
        require(bool(author.name.strip()), f"authors.{index}.name", "请填写作者姓名")
        require(
            _email_format_valid(author.email),
            f"authors.{index}.email",
            "请填写有效的作者邮箱；格式检查不代表身份或邮箱已核实",
        )
    require(
        sum(author.corresponding for author in data.authors) == 1,
        "authors.corresponding",
        "请选择且仅选择1位通讯作者",
    )
    require("manuscript" in file_purposes, "files.manuscript", "请上传稿件文件")
    require(
        "blinded_manuscript" in file_purposes,
        "files.blinded_manuscript",
        "请上传供匿名评审使用的稿件文件",
    )
    declarations = data.declarations
    require(declarations.originality, "declarations.originality", "请由作者本人确认原创性声明")
    require(declarations.copyright, "declarations.copyright", "请由作者本人确认版权声明")
    require(
        declarations.competing_interests != "unanswered",
        "declarations.competing_interests",
        "请由作者本人回答利益冲突声明",
    )
    if declarations.competing_interests == "declared":
        require(
            bool(declarations.competing_interests_text.strip()),
            "declarations.competing_interests_text",
            "请说明已声明的利益冲突",
        )
    require(
        declarations.ethics != "unanswered",
        "declarations.ethics",
        "请由作者本人回答伦理审批适用性",
    )
    if declarations.ethics == "approved":
        require(
            bool(declarations.ethics_reference.strip()),
            "declarations.ethics_reference",
            "请填写伦理批准机构或批准编号",
        )
    return missing
