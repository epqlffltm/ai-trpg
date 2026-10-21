# asset-server/tests/probes.py

"""
테스트에서만 붙이는 주소. 주소에 값이 든 틀(/probes/{item_id}/read)이 로그와 메트릭에 틀로 남는지 볼 때 쓴다.

뼈대의 서버에는 아직 값이 든 주소가 없다(#564). 계정 페르소나(#565)의 주소가 생기면 그것으로 바꿔도 된다.
"""

from fastapi import FastAPI, HTTPException, status

from app.main import API_PREFIX

# 붙이는 주소의 틀. 로그의 route 와 메트릭의 route label 이 이 글이어야 한다
PROBE_ROUTE = f'{API_PREFIX}/probes/{{item_id}}/read'


async def read_probe(item_id: int) -> None:
    """늘 404 다. 없는 것을 읽으려 한 요청처럼 끝난다."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'{item_id} 은 없다')


def add_probe_route(app: FastAPI) -> None:
    """앱에 테스트용 주소를 붙인다."""
    app.add_api_route(PROBE_ROUTE, read_probe, methods=['POST'], status_code=status.HTTP_200_OK)
