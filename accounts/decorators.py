"""
Role decorators.

Authorisation is enforced here, at the view layer, rather than by hiding links
in templates. A hidden link is not a control -- anyone can type the URL.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import User


def _role_required(required_role):
    """Build a decorator that admits only logged-in users holding `required_role`."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role != required_role:
                # 403 rather than a redirect: the user is authenticated and
                # this is a real refusal, not a prompt to sign in.
                raise PermissionDenied("لا تملك صلاحية الوصول إلى هذه الصفحة.")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


company_required = _role_required(User.Role.COMPANY)
seeker_required = _role_required(User.Role.JOB_SEEKER)
