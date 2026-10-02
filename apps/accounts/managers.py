# apps/accounts/managers.py
from django.contrib.auth.base_user import BaseUserManager


class TUserManager(BaseUserManager):
    """
    Same shape as TSP's CustomUserManager. username has no independent
    identity here — it always mirrors email, the same rule SignupForm
    already applies, so callers only ever pass email.
    """
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        extra_fields.setdefault('username', email)
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('status', self.model.Status.APPROVED)
        extra_fields.setdefault('role', self.model.Role.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)

    def get_by_identifier(self, identifier):
        """Find a user by email or phone. Returns None if nothing matches."""
        identifier = (identifier or '').strip()
        if not identifier:
            return None
        if '@' in identifier:
            return self.filter(email__iexact=identifier).first()
        if identifier.replace('+', '').isdigit():
            return self.filter(phone=identifier).first()
        return None