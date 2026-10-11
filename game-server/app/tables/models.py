# game-server/app/tables/models.py

"""
테이블의 모델. 테이블은 시나리오의 판 하나를 가져와 AI GM 과 플레이하는 자리다.

테이블 여섯이 있다.
  - game_tables: 테이블 자신. 방장, 어느 판에서 왔는지, 판의 복사본, 정원, 상태.
  - table_members: 테이블에 앉은 사람과 그 사람의 캐릭터(이름과 설명: 글).
  - table_sheets: 앉은 사람의 캐릭터 시트(능력치와 HP: 숫자). 게임을 시작할 때 생긴다.
    캐릭터가 죽어 새 캐릭터를 들이면 하나 더 생긴다. 죽은 캐릭터의 시트는 지우지 않는다.
  - table_rolls: 주사위로 굴린 능력치의 점수들. 사람이 나가도 남는다.
  - table_npcs: 로어북의 인물 항목마다의 숫자와 생사. 게임을 시작할 때 생긴다.
  - table_injuries: 캐릭터와 NPC 가 입은 부상. 나은 것도 지우지 않는다.

판은 고치지 않는다. 테이블은 만들 때 판의 내용을 통째로 복사해 온다(content). 이 복사본도 고치지 않는다.
플레이하면서 바뀌는 것(캐릭터의 HP, NPC 의 생사)은 따로 칸을 둔다(table_sheets, table_npcs).
문서 안의 값은 DB 가 검사하지 못하고, 하나를 바꾸려고 문서를 통째로 다시 쓰게 된다.

스키마 이름을 적지 않는다. 연결의 search_path 가 정한다(app/core/database.py).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.assets.models import (
    CHARACTER_DESCRIPTION_MAX_LENGTH,
    CHARACTER_NAME_MAX_LENGTH,
    CREATOR_MADE_MODES,
    DEFAULT_CHARACTER_MODES,
    TABLE_MAX_PLAYERS,
    TITLE_MAX_LENGTH,
    CharacterMode,
    NarrationStyle,
    Rating,
    all_of,
    at_most,
    none_of,
    one_of,
)
from app.core.database import Base

# 초대 코드의 길이(글자 수). 코드를 아는 사람만 테이블에 들어온다
INVITE_CODE_LENGTH = 12
# 테이블의 비밀번호. 로비에 보이는 테이블을 아는 사람끼리만 쓰려고 건다
TABLE_PASSWORD_MIN_LENGTH = 4
TABLE_PASSWORD_MAX_LENGTH = 64


class DeathCause(enum.StrEnum):
    """캐릭터가 죽은 까닭. 이벤트에 적는다."""

    # 죽음의 굴림에서 실패가 다 모였다. 규칙이 정했다
    DEATH_SAVE = 'death_save'
    # 쓰러진 캐릭터를 플레이어가 스스로 보냈다
    GAVE_UP = 'gave_up'


class TableStatus(enum.StrEnum):
    """테이블의 상태. 한 방향으로만 나아간다."""

    # 모집 중. 사람이 들어오고 캐릭터를 만든다
    RECRUITING = 'recruiting'
    # 진행 중. 방장이 시작했다. 새로 들어올 수 없고 캐릭터를 바꿀 수 없다.
    # 캐릭터가 죽은 사람만 새 캐릭터를 들인다(app/tables/replacements.py)
    PLAYING = 'playing'
    # 끝남. 방장이 끝냈거나 모두 나갔다
    ENDED = 'ended'


class InjurySource(enum.StrEnum):
    """부상이 어떻게 생겼나."""

    # 큰 타격이나 쓰러짐에 부상 표를 굴려서
    INJURY_TABLE = 'injury_table'
    # 노려 쳐서(#114 나)
    CALLED_SHOT = 'called_shot'
    # 오래 가는 부상이 나을 때 후유증 표를 굴려서(#114 다)
    AFTERMATH = 'aftermath'


class NpcStatus(enum.StrEnum):
    """
    NPC 의 생사. HP 와 따로 적는다. HP 가 0 인 NPC 는 쓰러졌거나 죽었는데, HP 만으로는 둘을 가를 수 없다.

    쓰러진 NPC 는 혼자서 깨어나지 못한다(의식이 없다). 죽음의 굴림은 없다. 회복을 받으면 일어난다.
    죽은 NPC 는 되돌리지 못한다.
    """

    ALIVE = 'alive'
    DOWNED = 'downed'
    DEAD = 'dead'


class GameTable(Base):
    """
    테이블 하나.

    방장은 테이블을 만든 사람이다. 방장이 나가면 남은 사람 중 가장 먼저 들어온 사람이 방장이 된다.
    """

    __tablename__ = 'game_tables'
    __table_args__ = (
        CheckConstraint(one_of('status', TableStatus), name='status_allowed'),
        CheckConstraint(one_of('rating', Rating), name='rating_allowed'),
        CheckConstraint(f'capacity BETWEEN 1 AND {TABLE_MAX_PLAYERS}', name='capacity_range'),
        CheckConstraint('opening_index >= 0', name='opening_index_not_negative'),
        # 비밀번호는 로비에 보이는 테이블에만 건다. 보이지 않는 테이블은 초대 코드가 그 일을 한다
        CheckConstraint('password_hash IS NULL OR is_public', name='password_needs_public'),
        # 방식이 하나는 있어야 한다. 하나도 없으면 아무도 캐릭터를 정할 수 없다
        CheckConstraint(
            f'cardinality(character_modes) >= 1 AND {all_of("character_modes", CharacterMode)}',
            name='character_modes_allowed',
        ),
        CheckConstraint(one_of('narration_style', NarrationStyle), name='narration_style_allowed'),
    )

    # API 주소에 드러나는 값이다. 순서대로 늘어나는 정수면 테이블이 몇 개인지 추측할 수 있다
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 방장. 인증 서버의 public_id 다. "내가 방장인 테이블"을 찾을 일이 있어 색인을 건다
    host_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)

    # 어느 판에서 왔는가. 플레이할 때는 읽지 않는다(content 를 읽는다). 출처를 남기는 것이다.
    # 제작자에게 수익을 나눌 때, 판이 바뀌었다고 알려 줄 때 쓴다.
    # RESTRICT: 테이블이 가리키는 판의 행은 지울 수 없다
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('scenario_versions.id', ondelete='RESTRICT'), index=True)

    # 시나리오의 제목. content 안에도 있지만, 목록을 보여 줄 때 큰 문서를 열지 않으려고 따로 둔다
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH))

    # 판의 복사본. 플레이에 필요한 것이 이 안에 다 있다. 모양은 판의 것과 같다(scenarios/snapshot.py).
    # GM 전용 글이 들어 있다. 참가자에게 그대로 내주면 안 된다
    content: Mapped[dict] = mapped_column(JSONB)

    # 고른 스타팅. content 의 openings 에서 몇 번째인가(0 부터). 테이블을 만드는 사람이 고른다
    opening_index: Mapped[int] = mapped_column(SmallInteger)

    # 정원. 방장을 포함해 몇 명까지 앉는가
    capacity: Mapped[int] = mapped_column(SmallInteger)

    status: Mapped[str] = mapped_column(String(20), default=TableStatus.RECRUITING)

    # 등급. 판의 것을 복사해 둔다. 누가 들어올 수 있는지를 문서를 열지 않고 판단한다
    rating: Mapped[str] = mapped_column(String(20))

    # 초대 코드. 이 코드를 아는 사람이 테이블에 들어온다. 방장이 참가자를 내보내면 새로 만든다
    invite_code: Mapped[str] = mapped_column(String(INVITE_CODE_LENGTH), unique=True)

    # 로비의 목록에 보이는가. 방장이 테이블을 만들 때 정한다. 나중에 바꾸지 않는다.
    # 보이는 테이블에는 초대 코드 없이도 들어올 수 있다
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    # 이 테이블에서 허용하는 캐릭터 방식들. 판이 허용한 것 중에서 방장이 고른다. 만든 뒤에는 바꾸지 않는다.
    # 이 칸이 생기기 전에 만든 테이블은 둘 다 허용한다. 그때는 프리젠을 고를 수도 직접 만들 수도 있었다
    character_modes: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), default=lambda: list(DEFAULT_CHARACTER_MODES), server_default=text("'{pregen,custom}'")
    )

    # 비밀번호. 그대로 두지 않고 계산한 값을 둔다(passwords.py). 비어 있으면 비밀번호가 없는 것이다.
    # 로비에서 들어올 때만 묻는다. 초대 코드로 들어올 때는 묻지 않는다. 방장이 직접 부른 사람이다
    password_hash: Mapped[str | None] = mapped_column(String(200))

    # GM 의 서술 문체. 만들 때 방장이 고르고, 고르지 않으면 판의 추천 문체다. 방장은 진행 중에도 바꿀 수 있다.
    # 판은 바뀌지 않으므로 "추천을 따른다"와 "추천과 같은 것을 골랐다"는 같다. 그래서 비워 두지 않고 늘 적어 둔다.
    # 로비의 목록이 판의 복사본을 열지 않고 문체를 보여 준다.
    # 이 칸이 생기기 전에 만든 테이블은 정통이다. 그 테이블의 판도 정통을 추천하는 것으로 읽힌다
    narration_style: Mapped[str] = mapped_column(String(20), server_default=text("'classic'"))

    # 이 테이블에 적힌 마지막 이벤트의 번호(app/events/models.py). 아직 없으면 0 이다.
    # 이벤트를 적을 때마다 하나씩 올린다. 테이블을 잠근 채로 올리므로 번호가 겹치지 않는다.
    # server_default: DB 에도 기본값을 둔다. 이 칸이 생기기 전에 만든 테이블은 0 에서 시작한다
    last_sequence: Mapped[int] = mapped_column(Integer, default=0, server_default=text('0'))

    # 이 테이블에 적힌 마지막 채팅의 번호(app/chat/models.py). 이벤트의 번호와 따로 센다. 방식은 같다
    last_message_sequence: Mapped[int] = mapped_column(Integer, default=0, server_default=text('0'))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 방장이 시작한 시각과 테이블이 끝난 시각. 아직이면 비어 있다
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 앉은 사람들. 들어온 순서다. 많아야 넷이라 테이블을 읽을 때 함께 읽는다.
    # delete-orphan: 이 목록에서 빠진 행은 DB 에서도 지운다(나가기, 내보내기)
    members: Mapped[list['TableMember']] = relationship(
        lazy='selectin', cascade='all, delete-orphan', order_by='TableMember.joined_at, TableMember.user_id'
    )

    # 이 테이블에서 주사위로 굴린 능력치의 점수들. 한 사람에 하나다. 테이블을 읽을 때 함께 읽는다.
    # 앉은 사람(members)이 아니라 테이블에 달려 있다. 나갔다가 다시 들어와도 굴린 것이 남아 있어야 한다
    rolls: Mapped[list['TableRoll']] = relationship(lazy='selectin', cascade='all, delete-orphan')


class TableMember(Base):
    """
    테이블에 앉은 사람 하나와 그 사람의 캐릭터.

    캐릭터는 이름과 설명이다. 들어온 직후에는 아직 없다(character_name 이 비어 있다).
    프리젠에서 가져왔으면 어느 프리젠인지 적어 둔다. 가져온 뒤에 이름과 설명을 고쳐도 그 자리는 이 사람의 것이다.

    캐릭터를 어느 방식으로 얻었는지도 적어 둔다(character_mode). 숫자가 어디서 왔는지는 테이블의 모두가 본다.
    능력치만 봐서는 직접 적은 것인지 다른 방식으로 정한 것인지 알 수 없다.

    여기 적힌 캐릭터는 이 사람의 "지금 캐릭터"다. 캐릭터가 죽어 새 캐릭터를 들이면 이 칸들을 새 캐릭터의 것으로 바꾼다.
    떠난 캐릭터의 이름과 프리젠은 그 캐릭터의 시트에 남는다(TableSheet).
    """

    __tablename__ = 'table_members'
    __table_args__ = (
        CheckConstraint(at_most('character_description', CHARACTER_DESCRIPTION_MAX_LENGTH), name='description_length'),
        # 프리젠 하나는 한 테이블에서 한 사람만 쓴다. 같은 인물이 둘이 될 수 없다.
        # 비어 있는 값(NULL)끼리는 겹치는 것으로 보지 않으므로, 직접 만든 캐릭터는 몇이든 된다
        UniqueConstraint('table_id', 'pregen_index'),
        # 캐릭터가 없는데 프리젠만 차지하고 있을 수 없다
        CheckConstraint('character_name IS NOT NULL OR pregen_index IS NULL', name='pregen_needs_character'),
        CheckConstraint(one_of('character_mode', CharacterMode), name='character_mode_allowed'),
        # 방식은 캐릭터가 있을 때만, 그리고 반드시 있다
        CheckConstraint('(character_mode IS NULL) = (character_name IS NULL)', name='character_mode_needs_character'),
        # 프리젠을 차지한 자리는 프리젠 방식이고, 프리젠 방식인 자리는 프리젠을 차지하고 있다.
        # IS NOT DISTINCT FROM: 방식이 비어 있어도 참·거짓이 나온다. = 로 견주면 "모름"이 되어 조건을 그냥 지나간다
        CheckConstraint(
            f"(pregen_index IS NOT NULL) = (character_mode IS NOT DISTINCT FROM '{CharacterMode.PREGEN}')",
            name='pregen_needs_pregen_mode',
        ),
        # 플레이어가 정한 능력치는 그런 방식의 캐릭터에만, 그리고 반드시 있다.
        # 제작자가 숫자를 적어 둔 방식(프리젠, 기본 시트)이 아니면 모두 그런 방식이다. 방식이 늘어도 이 조건은 그대로다
        CheckConstraint(
            f'(abilities IS NOT NULL) = {none_of("character_mode", CREATOR_MADE_MODES)}',
            name='abilities_need_player_made_mode',
        ),
        # 능력치는 이름표에서 점수로 가는 묶음이다. JSON 의 null 이나 숫자 하나가 "있는 능력치"로 적히지 못한다
        CheckConstraint("abilities IS NULL OR jsonb_typeof(abilities) = 'object'", name='abilities_is_object'),
    )

    # 두 칸을 합쳐 기본 키로 삼는다. 한 사람이 같은 테이블에 두 번 앉을 수 없다.
    # 테이블의 행이 지워지면 함께 지워진다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'), primary_key=True)
    # 인증 서버의 public_id. "내가 앉은 테이블"을 찾을 일이 있어 색인을 건다
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, index=True)

    # 캐릭터의 이름. 비어 있으면 아직 캐릭터를 만들지 않은 것이다
    character_name: Mapped[str | None] = mapped_column(String(CHARACTER_NAME_MAX_LENGTH))
    # 캐릭터의 설명. 턴마다 AI 의 입력에 들어간다
    character_description: Mapped[str] = mapped_column(Text, default='')

    # 캐릭터를 얻은 방식(CharacterMode). 캐릭터를 아직 만들지 않았으면 비어 있다
    character_mode: Mapped[str | None] = mapped_column(String(20))

    # 가져온 프리젠. content 의 pregens 에서 몇 번째인가(0 부터). 직접 만들었으면 비어 있다
    pregen_index: Mapped[int | None] = mapped_column(SmallInteger)

    # 플레이어가 직접 정한 능력치의 점수. 그런 방식으로 캐릭터를 만들었을 때만 있다.
    # 받을 때 이 테이블의 규칙과 견주어 봤다. 게임을 시작할 때 이것으로 시트를 만든다(app/tables/sheets.py).
    # none_as_null: 파이썬의 None 을 DB 의 NULL 로 적는다. 이 설정이 없으면 JSON 의 null 이라는 "값"이 적힌다.
    # 그 값은 IS NULL 이 아니어서, 능력치를 지웠는데도 DB 의 조건은 능력치가 있다고 본다
    abilities: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))

    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 이 사람이 이 테이블에서 받은 캐릭터 시트들. 받은 순서다. 게임을 시작하기 전에는 비어 있다.
    # 보통은 하나다. 캐릭터가 죽어 새 캐릭터를 들일 때마다 하나씩 는다.
    # selectin: 앉은 사람을 읽을 때 함께 읽는다. delete-orphan: 사람이 테이블에서 빠지면 시트도 지운다
    sheets: Mapped[list['TableSheet']] = relationship(
        lazy='selectin', cascade='all, delete-orphan', order_by='TableSheet.number'
    )

    @property
    def sheet(self) -> 'TableSheet | None':
        """지금 캐릭터의 시트. 가장 나중에 받은 것이다. 게임을 시작하기 전에는 None 이다."""
        return self.sheets[-1] if self.sheets else None

    @property
    def fallen(self) -> list['TableSheet']:
        """떠난 캐릭터들의 시트. 지금 캐릭터의 앞에 받은 것들이다. 모두 죽은 캐릭터다."""
        return self.sheets[:-1]


class TableSheet(Base):
    """
    테이블에 앉은 사람의 캐릭터 시트. 캐릭터의 숫자다.

    시작할 때의 숫자는 판에서 온다(프리젠의 시트나 기본 시트). 가져온 뒤로는 이 테이블의 것이다.
    플레이하면서 바뀌는 값(hp, 죽음의 굴림에서 센 것, 죽은 시각)이 여기 있다. 이 값은 엔진만 고친다.

    한 사람이 시트를 여럿 거쳐 간다. 캐릭터가 죽으면 새 캐릭터를 들이고, 새 캐릭터는 새 시트를 받는다.
    그래서 기본 키를 (table_id, user_id) 로 하지 않고 따로 두고, 몇 번째 캐릭터인지를 적는다(number).
    죽은 캐릭터의 시트는 지우지 않는다. 누가 이 테이블에서 죽었는지의 기록이다.

    누구의 시트인지도 적어 둔다(character_name, pregen_index). 받을 때 자리(table_members)에서 복사한다.
    자리의 칸들은 새 캐릭터를 들이면 새 캐릭터의 것으로 바뀐다. 떠난 캐릭터가 누구였는지는 여기에만 남는다.
    선언에 캐릭터 이름을 적어 두는 것과 같다(app/rounds/models.py).
    """

    __tablename__ = 'table_sheets'
    __table_args__ = (
        # 앉은 사람의 행이 지워지면(나가기, 내보내기, 테이블 삭제) 함께 지워진다
        ForeignKeyConstraint(
            ['table_id', 'user_id'], ['table_members.table_id', 'table_members.user_id'], ondelete='CASCADE'
        ),
        CheckConstraint('number >= 1', name='number_positive'),
        # 한 사람의 캐릭터에 같은 번호가 둘일 수 없다
        # 이름을 직접 적는다. 이름을 짓는 규칙은 첫 칸의 이름만 쓴다(app/core/database.py).
        # 맡기면 아래의 프리젠 조건과 이름이 같아진다
        UniqueConstraint('table_id', 'user_id', 'number', name='uq_table_sheets_number'),
        # 한 사람의 살아 있는 캐릭터는 하나뿐이다. 조건이 붙은 유일 색인이다.
        # 죽은 캐릭터의 시트(died_at 이 있는 것)는 이 색인에 들어가지 않으므로 몇 개든 된다.
        # 코드가 틀려서 캐릭터가 살아 있는데 새 시트를 줘도, DB 가 막는다
        Index('uq_table_sheets_living', 'table_id', 'user_id', unique=True, postgresql_where='died_at IS NULL'),
        # 프리젠 하나는 한 테이블에서 한 번만 시트를 받는다. 그 캐릭터가 죽은 뒤에도 그렇다.
        # 죽은 인물이 다른 사람의 캐릭터로 다시 걸어 들어오지 못한다.
        # 비어 있는 값(NULL)끼리는 겹치는 것으로 보지 않는다. 프리젠이 아닌 캐릭터는 몇이든 된다
        UniqueConstraint('table_id', 'pregen_index', name='uq_table_sheets_pregen'),
        CheckConstraint('max_hp >= 1', name='max_hp_positive'),
        # HP 는 0 아래로 내려가지 않고 최대를 넘지 않는다. 엔진의 실수를 DB 가 한 번 더 막는다
        CheckConstraint('hp BETWEEN 0 AND max_hp', name='hp_range'),
        CheckConstraint('death_successes >= 0 AND death_failures >= 0', name='death_saves_not_negative'),
        # 죽음의 굴림을 세는 것도, 죽는 것도 쓰러져 있을 때의 일이다. 일어나 있는 캐릭터에 그런 값이 남지 않는다
        CheckConstraint(
            'hp = 0 OR (death_successes = 0 AND death_failures = 0 AND died_at IS NULL)',
            name='death_only_when_downed',
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    table_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)

    # 이 사람의 몇 번째 캐릭터인가. 1 부터다. 시작할 때 받은 것이 1 이고, 새 캐릭터를 들일 때마다 하나씩 올라간다.
    # 시각으로 순서를 정하지 않는다. 번호는 겹치지 않고, 어느 것이 지금 캐릭터인지가 분명하다
    number: Mapped[int] = mapped_column(SmallInteger, default=1, server_default=text('1'))

    # 이 시트를 받은 캐릭터의 이름. 받을 때 자리에서 복사해 둔다
    character_name: Mapped[str] = mapped_column(String(CHARACTER_NAME_MAX_LENGTH))
    # 프리젠에서 온 캐릭터면 몇 번째 프리젠인가. 아니면 비어 있다
    pregen_index: Mapped[int | None] = mapped_column(SmallInteger)

    # 능력치의 점수. 능력치의 이름표에서 점수로 간다. 어떤 능력치가 있는지는 규칙이 정하므로 칸으로 두지 못한다.
    # 모양과 값은 판에 굳을 때 이미 검사했다(app/engine/sheet.py)
    abilities: Mapped[dict] = mapped_column(JSONB)

    # 최대 HP 와 지금의 HP. 정확해야 하고 자주 바뀌는 값이라 문서에 넣지 않고 칸으로 둔다
    max_hp: Mapped[int] = mapped_column(SmallInteger)
    hp: Mapped[int] = mapped_column(SmallInteger)

    # 죽음의 굴림에서 지금까지 센 성공과 실패(app/engine/death.py). 쓰러져 있는 동안만 센다.
    # 회복을 받아 일어나면 둘 다 0 으로 돌아간다. 이 값도 엔진만 고친다
    death_successes: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text('0'))
    death_failures: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text('0'))
    # 죽은 시각. 비어 있으면 살아 있다(쓰러져 있을 수는 있다). 한 번 적으면 지우지 않는다. 죽음은 되돌릴 수 없다
    died_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 이 캐릭터가 입은 부상들. 생긴 순서다. 나은 것도 들어 있다. 시트를 읽을 때 함께 읽는다(몇 개뿐이다)
    injuries: Mapped[list['TableInjury']] = relationship(
        lazy='selectin', cascade='all, delete-orphan', order_by='TableInjury.created_at, TableInjury.id'
    )


class TableRoll(Base):
    """
    한 사람이 한 테이블에서 주사위로 굴린 능력치의 점수들.

    자리(table_members)에 두지 않고 따로 둔다. 자리의 행은 나가면 지워진다.
    거기에 두면 나갔다가 다시 들어와서 새로 굴릴 수 있다. "한 테이블에서 한 번"이 지켜지지 않는다.
    그래서 테이블과 사람으로 찾는 행을 따로 두고, 사람이 나가도 지우지 않는다. 테이블이 지워질 때 함께 지워진다.

    행은 처음 굴릴 때 생긴다. 다시 굴리면 같은 행의 값을 바꾼다. 지난 값은 이벤트에 남아 있다.
    한 번 굴린 것은 캐릭터 하나에 쓴다. 캐릭터가 죽어 새 캐릭터를 들일 때는 새로 굴린다(character_number).
    굴린 점수를 어느 능력치에 놓았는지는 여기에 없다. 그것은 자리의 abilities 다.
    """

    __tablename__ = 'table_rolls'
    __table_args__ = (
        CheckConstraint('times_rolled >= 1', name='times_rolled_positive'),
        CheckConstraint('character_number >= 1', name='character_number_positive'),
        # 굴린 눈과 점수는 목록이다
        CheckConstraint("jsonb_typeof(dice) = 'array' AND jsonb_typeof(scores) = 'array'", name='rolls_are_arrays'),
    )

    # 두 칸을 합쳐 기본 키로 삼는다. 한 사람이 한 테이블에서 갖는 굴림은 하나다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'), primary_key=True)
    # 인증 서버의 public_id. 자리(table_members)를 가리키지 않는다. 자리가 없어져도 남아야 한다
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)

    # 굴린 눈. 점수 하나마다 눈의 목록이 하나다. 버린 눈도 들어 있다. 예: [[6, 5, 3, 1], [4, 4, 2, 2], ...]
    dice: Mapped[list] = mapped_column(JSONB)
    # 굴려서 나온 점수들. 굴린 순서다. 예: [14, 10, ...]. 플레이어가 이것을 능력치에 놓는다
    scores: Mapped[list] = mapped_column(JSONB)

    # 이 테이블에서 몇 번 굴렸는가. 처음 굴리면 1 이다. 캐릭터가 바뀌어도 이어서 센다
    times_rolled: Mapped[int] = mapped_column(SmallInteger, default=1)
    # 이 사람의 몇 번째 캐릭터를 위해 굴렸는가(TableSheet.number 와 같은 번호다). 시작 전에 굴린 것은 1 이다.
    # 지난 캐릭터를 위해 굴린 점수로 새 캐릭터를 만들지 못한다. 새 캐릭터는 새로 굴린다
    character_number: Mapped[int] = mapped_column(SmallInteger, default=1, server_default=text('1'))
    # 방장이 "한 번 더"를 줬는가. 다시 굴리면 꺼진다. 주어진 것은 한 번에 하나다
    reroll_granted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))

    rolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TableNpc(Base):
    """
    테이블 하나에서 로어북의 인물 항목 하나의 숫자와 생사. NPC 의 시트다.

    시작할 때 판의 인물 항목마다 하나씩 만든다. 숫자는 판의 NPC 시트나 기본 NPC 시트에서 온다(app/tables/npcs.py).
    가져온 뒤로는 이 테이블의 것이다. 같은 판으로 만든 다른 테이블의 같은 인물과 상관없다.
    지금 HP 와 생사는 엔진만 고친다. 방장도 손으로 고치지 못한다.

    누구인지는 항목의 ID(entry_id)로만 적는다. 이름과 내용은 판에 있다.
    로어북의 내용은 AI 만 읽는 글이라, 이 행을 앉은 사람에게 그대로 내주지 않는다.
    """

    __tablename__ = 'table_npcs'
    __table_args__ = (
        CheckConstraint('max_hp >= 1', name='max_hp_positive'),
        # HP 는 0 아래로 내려가지 않고 최대를 넘지 않는다. 엔진의 실수를 DB 가 한 번 더 막는다
        CheckConstraint('hp BETWEEN 0 AND max_hp', name='hp_range'),
        CheckConstraint(one_of('status', NpcStatus), name='status_allowed'),
        # 살아 있는 것과 HP 가 있는 것은 같다. 쓰러짐과 죽음은 HP 가 0 일 때만이다
        CheckConstraint(f"(status = '{NpcStatus.ALIVE}') = (hp > 0)", name='alive_when_hp'),
        CheckConstraint("jsonb_typeof(abilities) = 'object'", name='abilities_is_object'),
    )

    # 두 칸을 합쳐 기본 키로 삼는다. 한 테이블에서 인물 하나의 상태는 하나다.
    # 테이블의 행이 지워지면 함께 지워진다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'), primary_key=True)
    # 판(content)의 로어북 항목의 ID. 판은 문서라 외래 키를 걸지 못한다. 판을 고치지 않으므로 가리키는 항목은 늘 있다
    entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)

    # 능력치의 점수. 모양은 캐릭터 시트와 같다(TableSheet.abilities)
    abilities: Mapped[dict] = mapped_column(JSONB)
    max_hp: Mapped[int] = mapped_column(SmallInteger)
    hp: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(20), default=NpcStatus.ALIVE, server_default=text("'alive'"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 이 인물이 입은 부상들. 생긴 순서다. 나은 것도 들어 있다. 상태를 읽을 때 함께 읽는다
    injuries: Mapped[list['TableInjury']] = relationship(
        lazy='selectin', cascade='all, delete-orphan', order_by='TableInjury.created_at, TableInjury.id'
    )


class TableInjury(Base):
    """
    부상 하나. 캐릭터의 시트 하나나 NPC 하나가 입었다.

    어떤 부상인지는 이름(injury)으로만 적는다. 효과와 사실은 테이블의 판에 굳은 규칙에 있다(app/engine/ruleset.py).
    짧은 것은 풀릴 라운드(ends_after_round)가 적힌다. 그 라운드가 닫힐 때 풀린다.
    풀리거나 나으면 그 시각(ended_at)을 적고 지우지 않는다. 누가 언제 무엇을 입었는지의 기록이다.
    부상을 만들고 푸는 것은 엔진뿐이다(app/tables/injuries.py). 방장도 손으로 고치지 못한다.
    """

    __tablename__ = 'table_injuries'
    __table_args__ = (
        # 시트가 지워지면(사람이 나감) 함께 지워진다
        ForeignKeyConstraint(['sheet_id'], ['table_sheets.id'], ondelete='CASCADE'),
        ForeignKeyConstraint(
            ['table_id', 'npc_entry_id'], ['table_npcs.table_id', 'table_npcs.entry_id'], ondelete='CASCADE'
        ),
        # 입은 것은 캐릭터나 NPC 중 정확히 하나다
        CheckConstraint('(sheet_id IS NULL) <> (npc_entry_id IS NULL)', name='one_holder'),
        CheckConstraint(one_of('source', InjurySource), name='source_allowed'),
        CheckConstraint('round_number >= 1', name='round_number_positive'),
        # 풀리는 라운드는 생긴 라운드의 뒤다
        CheckConstraint('ends_after_round IS NULL OR ends_after_round > round_number', name='ends_after_start'),
        # 아직 낫지 않은 부상을 찾는 일이 라운드마다 있다
        Index('ix_table_injuries_active', 'table_id', postgresql_where='ended_at IS NULL'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 어느 테이블의 부상인가. 테이블의 행이 지워지면 함께 지워진다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'))
    # 입은 캐릭터의 시트. NPC 의 부상이면 비어 있다
    sheet_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # 입은 NPC(판의 로어북 인물 항목의 id). 캐릭터의 부상이면 비어 있다
    npc_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    # 규칙의 Injury.key
    injury: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20))
    # 생긴 라운드. 그 라운드가 닫힐 때 생겼다
    round_number: Mapped[int] = mapped_column(Integer)
    # 이 라운드가 닫힐 때 풀린다. 짧은 부상에만 있다. 오래 가는 것과 결손은 비어 있다
    ends_after_round: Mapped[int | None] = mapped_column(Integer)
    # 풀리거나 나은 시각. 비어 있으면 아직 입고 있다
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
