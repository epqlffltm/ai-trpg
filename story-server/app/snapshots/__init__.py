# story-server/app/snapshots/__init__.py

"""
장면 그림(#983). 모델의 답 하나를 골라 그 장면을 그림으로 만든다. 한 장마다 청구한다.

  - models.py: 한 장의 기록과 청구(snapshots)
  - prompt.py: 그림의 지시를 서버의 상태(세계관, 시각과 장소, 장면의 인물)와 그 답의 글로 만든다. DB 를 모른다
  - providers.py: 설정으로 그림 provider 를 고른다(ai_core 의 Nano Banana, ComfyUI, 가짜)
  - repository.py: 쿼리. 커밋하지 않는다
  - service.py: 한 장의 길(기록 → 홀드 → 그리기 → asset 에 맡기기 → 확정이나 반환)
  - router.py: API
  - settler.py: 끝나지 않은 청구를 마저 맡기는 작업
"""
