# auth-server/accounts/admin.py

"""
관리자 화면에 User 모델을 등록한다.

Django 의 UserAdmin 을 상속해 비밀번호 해싱과 변경 화면을 그대로 쓰고,
화면에 보이는 필드 구성만 이 프로젝트의 User 모델에 맞춘다.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # 목록 화면
    list_display = ('username', 'email', 'nickname', 'is_staff', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'nickname')
    ordering = ('-date_joined',)

    # 값이 자동으로 정해지는 필드는 화면에서 고칠 수 없게 한다
    readonly_fields = ('public_id', 'token_version', 'last_login', 'date_joined')

    # 수정 화면. 기본 구성에서 first_name, last_name 을 빼고 nickname, public_id 를 넣는다
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('프로필', {'fields': ('email', 'nickname', 'public_id')}),
        ('권한', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('기록', {'fields': ('token_version', 'last_login', 'date_joined')}),
    )

    # 추가 화면. 기본 구성은 아이디와 비밀번호만 묻는다.
    # email 과 nickname 이 필수라서 여기에 넣지 않으면 빈 값으로 저장된다
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'nickname', 'usable_password', 'password1', 'password2'),
        }),
    )
