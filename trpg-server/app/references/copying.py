# trpg-server/app/references/copying.py

"""
고른 참고 자료를 내 로어북의 항목과 내 도감의 몬스터로 옮기는 규칙(#482 4단계). DB 를 모르는 순수한 함수다.

제작자가 골라서 내 것으로 복사한다(2026-10-21 유저 결정). 복사한 뒤로는 제작자의 자산이다. 고치고 게시한다.
옮기는 것.
  - 이름과 글은 한국어로 옮긴 것(없으면 원본)이다. 글에는 수치가 없다(app/references/srd.py).
  - 로어북의 글은 500자, 도감의 이름은 50자까지다. 넘으면 문장의 끝에서 자른다.
  - 로어북: 물건은 물건, 몬스터는 종족 항목이다. 다른 이름(한국어 이름 등)을 키워드로 단다.
  - 도감: 몬스터만 받는다. 원본의 생물 분류를 엔진이 다루는 타입으로 바꾼다. 맞는 것이 없으면 기타다.
  - 원본의 수치(data)는 옮기지 않는다. 도감의 몬스터에는 수치가 없다(시나리오의 시트가 정한다).
"""

import re

from app.assets.bestiaries.models import MONSTER_CONTENT_MAX_LENGTH, MONSTER_NAME_MAX_LENGTH, MonsterKind
from app.assets.bestiaries.schemas import MonsterCreate
from app.assets.copies import Copy
from app.assets.lorebooks.schemas import EntryCreate
from app.assets.models import LORE_ENTRY_CONTENT_MAX_LENGTH, LORE_ENTRY_MAX_KEYWORDS, LORE_KEYWORD_MAX_LENGTH, LoreKind
from app.references.records import ReferenceKind, StoredReference
from app.references.retrieval import MIN_ALIAS_LENGTH

# 원본(SRD 5.1)의 생물 분류에서 엔진이 다루는 타입으로. 여기 없는 분류(용, 괴물, 악마 …)는 기타다
MONSTER_KINDS = {
    'humanoid': MonsterKind.HUMANOID,
    'beast': MonsterKind.BEAST,
    'swarm of tiny beasts': MonsterKind.BEAST,
    'undead': MonsterKind.UNDEAD,
    'construct': MonsterKind.CONSTRUCT,
}
# 참고 자료의 종류에서 로어북 항목의 종류로. 몬스터는 한 마리가 아니라 그 무리의 설명이라 종족이다
LORE_KINDS = {ReferenceKind.ITEM: LoreKind.ITEM, ReferenceKind.MONSTER: LoreKind.SPECIES}
# 문장의 끝. 마침표, 느낌표, 물음표와 특성을 나누는 쌍반점 뒤가 빈칸이거나 글의 끝이다
SENTENCE_END = re.compile(r'[.!?;](?=\s|$)')
# 문장의 끝을 찾지 못해 글자 수로 자를 때 붙이는 표시
ELLIPSIS = '…'


class NotAMonsterError(Exception):
    """몬스터가 아닌 줄을 도감에 넣으려 했다. keys 는 그런 줄의 key 들이다."""

    def __init__(self, keys: list[str]) -> None:
        super().__init__(', '.join(keys))
        self.keys = keys


def cut_text(text: str, limit: int) -> str:
    """
    글을 limit 자 안으로 줄인다. 넘지 않으면 그대로다.

    limit 안의 마지막 문장 끝에서 자른다. 쌍반점(특성의 구분)에서 잘렸으면 마침표로 맺는다.
    문장 끝이 없으면 글자 수로 자르고 '…' 을 붙인다.
    """
    if len(text) <= limit:
        return text
    ends = [match.end() for match in SENTENCE_END.finditer(text) if match.end() <= limit]
    if not ends:
        return text[: limit - len(ELLIPSIS)].rstrip() + ELLIPSIS
    cut = text[: ends[-1]].rstrip()
    return cut[:-1] + '.' if cut.endswith(';') else cut


def lore_keywords(reference: StoredReference) -> list[str]:
    """
    로어북 항목의 키워드. 다른 이름에서 고른다(한국어 이름이 맨 앞이다).

    한 글자 이름은 뺀다. 낱말 속("쥐었다")에서 잘못 걸린다(서술의 고르기와 같다).
    대소문자만 다른 이름은 하나만, 상한(5개, 30자)까지다.
    """
    keywords: list[str] = []
    seen: set[str] = set()
    for alias in reference.aliases:
        name = alias.strip()
        folded = name.casefold()
        if MIN_ALIAS_LENGTH <= len(name) <= LORE_KEYWORD_MAX_LENGTH and folded not in seen:
            keywords.append(name)
            seen.add(folded)
    return keywords[:LORE_ENTRY_MAX_KEYWORDS]


def monster_kind(reference: StoredReference) -> MonsterKind:
    """원본의 생물 분류(data.type)를 도감의 타입으로. 모르면 기타다."""
    return MONSTER_KINDS.get(str(reference.data.get('type', '')).casefold(), MonsterKind.OTHER)


def entry_copy(reference: StoredReference) -> Copy[EntryCreate]:
    """참고 자료 한 줄을 로어북 항목으로 옮길 것."""
    data = EntryCreate(
        name=reference.shown_name,
        keywords=lore_keywords(reference),
        content=cut_text(reference.shown_content, LORE_ENTRY_CONTENT_MAX_LENGTH),
        kind=LORE_KINDS[ReferenceKind(reference.kind)],
    )
    return Copy(reference_id=reference.id, source=reference.source, key=reference.key, data=data)


def monster_copy(reference: StoredReference) -> Copy[MonsterCreate]:
    """참고 자료 한 줄(몬스터)을 도감의 몬스터로 옮길 것. 이름이 길면 글자 수로 자른다."""
    data = MonsterCreate(
        name=reference.shown_name[:MONSTER_NAME_MAX_LENGTH].strip(),
        content=cut_text(reference.shown_content, MONSTER_CONTENT_MAX_LENGTH),
        kind=monster_kind(reference),
    )
    return Copy(reference_id=reference.id, source=reference.source, key=reference.key, data=data)


def check_monsters(references: list[StoredReference]) -> None:
    """모두 몬스터인지 본다. 아닌 줄이 있으면 그 key 들로 NotAMonsterError 다."""
    others = [reference.key for reference in references if reference.kind != ReferenceKind.MONSTER]
    if others:
        raise NotAMonsterError(others)
