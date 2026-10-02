# apps/accounts/backends.py (full replace)
from django.contrib.auth.backends import BaseBackend
from .models import TUser


class EUPBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        user = TUser.objects.get_by_identifier(username)
        if user is None:
            # Burn the same hashing time as a real check, so response speed
            # can't reveal which emails or phones have accounts.
            TUser().set_password(password)
            return None

        if user.check_password(password) and user.is_active:
            return user
        return None

    def get_user(self, user_id):
        try:
            return TUser.objects.get(pk=user_id)
        except TUser.DoesNotExist:
            return None