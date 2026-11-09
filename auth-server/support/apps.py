# auth-server/support/apps.py

"""
문의(고객센터)의 앱. 운영자 전용 관리 서버가 생기면 그리로 옮긴다(2026-11-09 결정).

옮기기 쉽게 accounts 와 앱을 나눈다. 이 앱이 accounts 에서 가져다 쓰는 것은 계정(User), 운영자 확인(roles),
메일 발송함(outbox), 시도 제한(throttles)뿐이다. accounts 는 탈퇴할 때 문의를 지우려고 이 앱의 모델 하나만 부른다.
"""

from django.apps import AppConfig


class SupportConfig(AppConfig):
    name = 'support'
    verbose_name = '문의'
