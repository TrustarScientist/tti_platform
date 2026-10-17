# tti_platform/settings_test.py
import os

# Never used (tests run on in-memory SQLite), but settings.py insists on a value at import time.
os.environ.setdefault('DATABASE_URL', 'postgresql://unused:unused@localhost:5432/unused')

from .settings import *  # noqa: E402,F401,F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    # The production storage needs collectstatic's manifest, which doesn't exist in tests.
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']  # fast, tests only