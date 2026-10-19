# game-server/app/ai_log/__init__.py

"""
AI 호출의 기록(ai_invocations)을 DB 에 쓰고, 보관 기한이 지난 원문을 비우는 곳(#497).

AI 를 부르는 코드(app/ai)는 호출 한 번의 값(결과, 사용량, 원가)을 CallRecord 로 넘기기만 한다
(app/ai/calls.py 의 CallLog).
그 값을 표에 쓰는 일과 표, 지우는 작업은 서비스의 몫이라 여기 둔다. 표 이름과 마이그레이션은 그대로다.
"""
