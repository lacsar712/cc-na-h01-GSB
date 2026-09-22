from .settings import *  # noqa: F401,F403

# 本地无 PostgreSQL 时跑测试用：DJANGO_SETTINGS_MODULE=config.settings_test
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
