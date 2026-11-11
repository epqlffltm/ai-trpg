# shared/catalog-core/src/catalog_core/tables.py

"""
서버의 모델 목록 표 셋을 묶어 넘기는 꾸러미.

표는 서버마다 제 Base 와 스키마로 만든다(서버의 app/catalog/models.py). 공용 코드가 쓰는 칸의 이름은 세 서버가 같다.
  - model: ai_models. slug, provider, api_model_id, display_name, vendor, grade, supports_reasoning,
    supports_temperature, token_limit_field, reasoning_style, enabled, retires_on
  - cost: ai_model_costs. id, model_slug, input_per_mtok, cached_input_per_mtok, cache_write_per_mtok,
    output_per_mtok, effective_from, checked_on, note
  - snapshot: ai_model_snapshots. id, model_slug, previous_api_model_id, api_model_id, note
서버만의 칸(allows_adult, vendor_fallback)은 모른다.
들여오기가 회사를 바꿀 때 그 칸을 고칠 자리(on_vendor_change)만 연다.

공용 코드가 칸까지 정의하지 않고 서버의 표를 꾸러미로 받는다. 표의 모양(제약, 색인, 서버만의 칸)이 서버마다 조금씩 달라
칸까지 공용으로 올리면 서버마다 마이그레이션을 다시 맞춰야 한다. 칸의 이름이 어긋나면 서버의 테스트(실제 DB)가 잡는다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


def keep_server_switches(model: Any) -> None:
    """회사가 바뀌어도 서버만의 칸을 그대로 둔다. 서버만의 칸이 회사와 무관한 서버(chat, story)의 것이다."""


@dataclass(frozen=True)
class CatalogTables:
    """서버의 표 셋(ORM 클래스). 서버가 app/catalog/models.py 에 하나 만들어 둔다."""

    model: type[Any]
    cost: type[Any]
    snapshot: type[Any]
    # 들여오기가 모델의 회사를 바꾸기 직전에 부른다. 회사에 묶인 서버만의 칸을 고친다(trpg 의 회사의 대체 모델)
    on_vendor_change: Callable[[Any], None] = keep_server_switches
