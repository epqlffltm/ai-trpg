# trpg-server/app/portraits/__init__.py

"""
제작자가 올린 캐릭터 그림(#983). 프리젠에 붙여 장면 그림의 참고 그림(얼굴 맞추기)으로 넘길 그림이다.

  - models.py: 올린 그림의 기록(portraits). 그림 자체는 asset 서버에 있다
  - repository.py: 기록을 넣고 찾는다
  - service.py: 올리기(asset 에 맡기고 기록), 목록, 그림의 바이트
  - router.py: 주소

플레이어가 직접 만든 캐릭터에는 그림을 받지 않는다(2026-11-05 유저 결정). 실제 사람의 사진이 그림 모델에 들어갈 수 있다.
"""
