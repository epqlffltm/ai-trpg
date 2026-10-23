# trpg-server/app/transcripts/labels.py

"""
기록에 쓰는 이 판의 이름들(#403). 이벤트에는 이름표(dex, medium, broken_arm)가 적혀 있고, 이름은 판의 규칙에 있다.

받을 범위를 정할 때(app/transcripts/reading.py) 판에서 한 번 꺼내 두고, 글로 바꿀 때(markdown.py) 쓴다.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from app.assets.scenarios.snapshot import Snapshot


@dataclass(frozen=True)
class Labels:
    """이 판의 규칙에 적힌 이름들. 이름표(dex, medium, broken_arm)에서 이름(민첩, 보통, 팔 골절)으로 간다."""

    abilities: Mapping[str, str] = field(default_factory=dict)
    difficulties: Mapping[str, str] = field(default_factory=dict)
    injuries: Mapping[str, str] = field(default_factory=dict)
    # 판의 화폐의 이름과 단위(#278). 돈이 없는 판이면 비어 있다
    currency_name: str = ''
    currency_unit: str = ''


def labels_of(snapshot: Snapshot) -> Labels:
    """판의 규칙에서 이름들을 꺼낸다."""
    rules = snapshot.rulebook.rules
    return Labels(
        abilities={ability.key: ability.name for ability in rules.abilities},
        difficulties={difficulty.key: difficulty.name for difficulty in rules.difficulties},
        injuries={injury.key: injury.name for injury in rules.injuries},
        currency_name=snapshot.currency.name if snapshot.currency else '',
        currency_unit=snapshot.currency.unit if snapshot.currency else '',
    )
