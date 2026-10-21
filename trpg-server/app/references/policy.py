# trpg-server/app/references/policy.py

"""
참고 자료(#482)를 켤 수 있는지 정하는 규칙. DB 도 HTTP 도 모르는 순수한 함수다.

세계관의 제작자가 허용하고(world.references_allowed), 그 안에서 방장이 방 설정으로 켠다(game_tables.references_enabled).
세계관이 없는 판은 지킬 설정이 없어 켤 수 있다(2026-10-21 유저 결정).
"""

from app.assets.scenarios.snapshot import Snapshot


def references_allowed(snapshot: Snapshot) -> bool:
    """이 판에서 방장이 참고 자료를 켤 수 있는가. 세계관이 없거나, 세계관이 허용했으면 켤 수 있다."""
    return snapshot.world is None or snapshot.world.references_allowed
