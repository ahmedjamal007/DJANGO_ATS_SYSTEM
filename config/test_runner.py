"""
Test runner that swaps in a cheap password hasher.

Django hashes passwords with PBKDF2 and a high iteration count, which is the
right choice in production and the wrong one in a test suite that creates a
user per test. Swapping in MD5 for test runs only cuts the suite from minutes
to seconds.

MD5 is not a safe password hash. It is confined to this runner, which Django
only uses for `manage.py test`, so it never touches a real database.
"""

from django.conf import settings
from django.test.runner import DiscoverRunner


class FastTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
