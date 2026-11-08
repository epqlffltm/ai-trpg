# trpg-server/app/rounds/improvised.py

"""
즉흥 조우(#254). 서술(AI)이 판의 조우 표에서 몬스터의 등장을 고르고, 엔진이 검증해 받아들인다.

AI 는 고르기만 한다. 무엇이 나올 수 있는지, 받아들일지, 몇 마리를 어디에 놓을지는 엔진이 정한다.
  - 켜기: 판의 improvised_encounters 가 1 이상이다(제작자가 정한 테이블 하나의 횟수). 0 이면 꺼져 있다.
  - 고를 거리(options): 살아 있는 캐릭터가 선 장소마다, 그 장소에서 지금 때에 쓰는 조우 표(app/rounds/wanders.py 의
    table_for, 그 장소의 표가 없으면 판의 기본 표)의 몬스터 줄들이다. 마리 수는 표의 줄에 적힌 것이다.
    그 장소에 살아 있는 몬스터가 있거나 표의 확률이 0(안전한 곳)이면 빼고(무작위 조우와 같다),
    테이블의 횟수를 다 썼으면 하나도 없다.
    고를 거리는 테이블의 지금 상태로만 정한다. 닫는 중인 라운드는 서술을 받아들일 때까지 상태가 바뀌지 않으므로
    서술을 부탁할 때와 받아들일 때 같은 목록이 나온다(번호도 같다). 서술을 몇 번 다시 맡겨도 같다.
  - 고르기: 서술의 맨 끝에 따로 한 줄 `[[조우 번호]]` 를 적는다(app/rounds/prompt.py 의 [즉흥 조우]).
    받아들일 때 장면에서 그 줄을 뗀다. 장면의 다른 곳에 적힌 것도 뗀다. 여럿이면 마지막 것 하나만 본다.
    미리 보기에서도 가린다(TaglessPreview).
  - 받아들이기: 번호가 고를 거리에 있으면 그 장소에 그 줄의 마리 수만큼 놓고, 테이블의 수를 하나 늘린다.
    없는 번호, 다 쓴 횟수면 아무 일도 없다(장면만 받는다). 한 라운드에 하나뿐이다(표식은 하나만 본다).
    놓는 것은 무작위 조우와 같다(번호를 잇고, 기습은 그 줄에 적힌 것). 일행이 만나는 것은 다음 라운드다.

DB 를 모른다(이벤트를 적는 record 말고). 테이블과 그 몬스터들을 받아 새 마리를 만든다.
저장(session.add)은 부른 쪽이 한다.
"""

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import Snapshot, WanderMonsterSnapshot, monster_of, place_entries
from app.calendar.clock import read_time
from app.events import recorder
from app.events.models import EventType, TableEvent
from app.rounds import wanders
from app.rounds.narrator import EncounterNote, Preview
from app.tables import sheets
from app.tables.models import GameTable, TableMonster

# 무엇이 불렀나. 나온 무리(monsters_appeared)의 cause 다. 무작위 조우(arrive, rest)와 나눈다
CAUSE = 'improvised'
# 서술이 고른 것을 적는 표식. 줄 하나에 이것만 있다. 번호는 고를 거리의 번호(1 부터)다
TAG = re.compile(r'\[\[\s*조우\s*(\d{1,3})\s*\]\]')
# 미리 보기에서 표식이 될 수 있는 앞부분. 이것으로 끝나는 동안은 잡아 둔다
TAG_START = '[['


@dataclass(frozen=True)
class Option:
    """고를 거리 하나. 번호, 어디에, 무엇이, 몇 마리. line 은 조우 표의 그 줄이다."""

    number: int
    place_id: uuid.UUID
    place_name: str
    monster_name: str
    count: int
    line: WanderMonsterSnapshot


def remaining(table: GameTable, snapshot: Snapshot) -> int:
    """이 테이블이 아직 받아들일 수 있는 즉흥 조우의 수. 꺼져 있으면 0 이다."""
    return max(0, snapshot.improvised_encounters - table.improvised_encounters)


def standing_places(table: GameTable) -> list[uuid.UUID]:
    """살아 있는 캐릭터가 선 장소들. 앉은 순서의 처음 나온 차례이고 겹치지 않는다. 맵에 서 있지 않은 사람은 뺀다."""
    places: list[uuid.UUID] = []
    for member in table.members:
        sheet = member.sheet
        if sheet is None or sheets.is_dead(member) or sheet.place_id is None or sheet.place_id in places:
            continue
        places.append(sheet.place_id)
    return places


def options(table: GameTable, snapshot: Snapshot, monsters: list[TableMonster]) -> list[Option]:
    """
    지금 고를 수 있는 것들. 장소의 차례, 그 안에서 표의 줄의 차례로 1 부터 번호를 붙인다.

    꺼져 있거나 횟수를 다 썼거나 조우 표가 없으면 빈 목록이다.
    """
    if remaining(table, snapshot) <= 0 or not snapshot.wanders:
        return []
    time = read_time(table.clock.minutes).time_of_day
    names = {entry.id: entry.name for entry in place_entries(snapshot)}
    found: list[Option] = []
    for place_id in standing_places(table):
        rule = wanders.table_for(snapshot, place_id, time)
        # 확률이 0 인 표는 제작자가 안전하게 둔 곳이다. 즉흥 조우도 오지 않는다
        if rule is None or rule.chance <= 0 or wanders.has_living_monster(monsters, place_id):
            continue
        for line in rule.monsters:
            monster = monster_of(snapshot, line.monster_id)
            number = len(found) + 1
            found.append(Option(number, place_id, names.get(place_id, ''), monster.name, line.count, line))
    return found


def to_notes(found: list[Option]) -> list[EncounterNote]:
    """고를 거리를 서술자에게 줄 모양으로. 번호, 장소, 몬스터, 마리 수다."""
    return [EncounterNote(one.number, one.place_name, one.monster_name, one.count) for one in found]


def split_tag(text: str) -> tuple[str, int | None]:
    """
    장면에서 표식을 떼고 (장면, 고른 번호)를 돌려준다. 표식이 없으면 번호는 None 이다.

    표식이 여럿이면 마지막 것을 본다. 표식만 있던 줄은 지우고, 장면의 끝의 빈 줄을 떼어 낸다.
    """
    found = TAG.findall(text)
    if not found:
        return text, None
    cleaned = TAG.sub('', text)
    lines = [line.rstrip() for line in cleaned.split('\n')]
    return '\n'.join(lines).strip(), int(found[-1])


@dataclass(frozen=True)
class Accepted:
    """받아들인 즉흥 조우. 나온 무리의 이벤트의 모양(met)과 새 마리들(made)."""

    met: dict
    made: list[TableMonster]


def accept(
    table: GameTable, snapshot: Snapshot, monsters: list[TableMonster], number: int | None, round_number: int
) -> Accepted | None:
    """
    서술이 고른 번호를 받아들인다. 고를 거리에 있으면 몬스터를 놓고 테이블의 수를 늘린다. 아니면 None.

    monsters 는 테이블의 몬스터 전부다. 새 마리를 여기에 더한다. 저장은 부른 쪽이 한다.
    """
    if number is None:
        return None
    chosen = next((option for option in options(table, snapshot, monsters) if option.number == number), None)
    if chosen is None:
        return None
    trigger = wanders.Trigger(place_id=chosen.place_id, cause=CAUSE, minutes=table.clock.minutes)
    made = wanders.spawn(table, snapshot, monsters, trigger, chosen.line)
    table.improvised_encounters += 1
    return Accepted(wanders.met_document(snapshot, trigger, chosen.line, made, round_number), made)


def record(session: AsyncSession, table: GameTable, accepted: Accepted | None, cause: TableEvent | None) -> None:
    """받아들인 즉흥 조우를 이벤트로 적는다(monsters_appeared, cause improvised). 라운드의 닫힘에 잇는다."""
    if accepted is not None:
        recorder.record(session, table, EventType.MONSTERS_APPEARED, payload=accepted.met, cause=cause)


def held_length(text: str) -> int:
    """
    미리 보기에서 잡아 둘 끝의 글자 수. 끝에 열린 표식(`[[` 뒤에 아직 닫히지 않은 것)이 있으면 그 길이다.

    `[` 하나로 끝나도 잡아 둔다. 다음 조각이 `[` 이면 표식이 된다.
    """
    start = text.rfind(TAG_START)
    if start != -1 and ']]' not in text[start:]:
        return len(text) - start
    return 1 if text.endswith('[') else 0


@dataclass
class TaglessPreview:
    """
    미리 보기에서 즉흥 조우의 표식을 가려서 넘긴다. Preview 모양을 따른다(app/rounds/narrator.py).

    pending 은 표식의 앞부분일 수 있어 아직 넘기지 않은 글이다. 시도가 끝날 때 남은 몇 글자는 넘기지 않는다.
    서술이 끝나면 표식을 뗀 장면(gm_narration)이 따로 간다.
    """

    inner: Preview
    pending: str = field(default='')

    def begin(self) -> None:
        """새 시도가 시작됐다. 앞의 시도에서 잡아 둔 글은 버린다."""
        self.pending = ''
        self.inner.begin()

    def text(self, piece: str) -> None:
        """조각을 모아, 표식을 떼고, 표식이 될 수 없는 앞부분을 넘긴다."""
        self.pending = TAG.sub('', self.pending + piece)
        cut = len(self.pending) - held_length(self.pending)
        ready, self.pending = self.pending[:cut], self.pending[cut:]
        if ready:
            self.inner.text(ready)
