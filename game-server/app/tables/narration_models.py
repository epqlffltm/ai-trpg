# game-server/app/tables/narration_models.py

"""
테이블의 서술 모델을 바꾼다. 방장만 한다.

모델은 라운드를 열 때 그 라운드의 것으로 굳는다(app/rounds/opener.py). 그래서 바꾼 값은 다음 라운드부터 쓴다.
지금 열려 있는 라운드는 연 때의 모델의 값으로 청구를 적어 두었다. 서술 등급(app/tables/tiers.py)과 같다.

고를 수 있는 모델만 된다(app/tables/model_picker.py). null 로 바꾸면 서버의 기본(서술 등급)으로 돌아간다.
바꾼 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다. 각자 값을 내므로 모두가 알아야 한다.

HTTP 를 모른다. 테이블을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.tables.model_picker import ModelPicker, require_pickable
from app.tables.models import GameTable
from app.tables.schemas import NarrationModelUpdate
from app.tables.service import lock_seated, save
from app.tables.state import require_host, require_not_ended


async def change_narration_model(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: NarrationModelUpdate, picker: ModelPicker
) -> GameTable:
    """
    방장이 서술 모델을 바꾼다.

    방장이 아니면 NotHostError, 끝난 테이블이면 TableConflictError, 고를 수 없는 모델이면 TableOptionError.
    지금과 같은 값이면 아무것도 적지 않는다. 바뀐 것이 없는데 이벤트가 쌓이지 않게 한다.
    고를 수 있는지는 잠근 뒤, 값이 바뀔 때만 본다. 같은 값이면 결제 서버의 가격 목록을 묻지 않는다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)

    if data.narration_model == table.narration_model:
        return table
    await require_pickable(session, picker, data.narration_model)

    table.narration_model = data.narration_model
    payload = {'narration_model': data.narration_model}
    recorder.record(session, table, EventType.NARRATION_MODEL_CHANGED, actor_id=host_id, payload=payload)
    return await save(session, table)
