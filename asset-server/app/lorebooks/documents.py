# asset-server/app/lorebooks/documents.py

"""
로어북의 판에 굳히는 문서의 모양(#672). 캐릭터를 게시할 때 이 문서가 캐릭터의 판에 복사된다.

판의 형식(format)에 번호를 둔다. 칸이 늘면 번호를 올린다(캐릭터의 판과 같은 방식).
  - 1: 처음의 칸(이름, 항목들. 항목은 id, 이름, 종류, 키워드, 내용, 상시 여부)
DB 를 모르는 순수한 함수다.
"""

from pydantic import BaseModel, ConfigDict

from app.lorebooks.models import Lorebook, LoreKind

# 판의 형식. 칸을 바꾸면 올린다
LOREBOOK_FORMAT = 1


class LoreEntryDocument(BaseModel):
    """
    항목 하나. constant 면 늘 모델에 간다. 아니면 최근 대화에 키워드가 나올 때 간다(고르는 것은 chat 이다).
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    id: str
    name: str
    kind: LoreKind
    keywords: list[str]
    content: str
    constant: bool


class LorebookDocument(BaseModel):
    """판에 굳힌 로어북. 설명은 만든 사람이 보는 것이라 판에 넣지 않는다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    format: int
    name: str
    entries: list[LoreEntryDocument]


def build_document(lorebook: Lorebook) -> LorebookDocument:
    """초안으로 판의 문서를 만든다."""
    return LorebookDocument(
        format=LOREBOOK_FORMAT,
        name=lorebook.name,
        entries=[LoreEntryDocument.model_validate(entry) for entry in lorebook.entries],
    )
