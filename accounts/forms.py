"""Registration form. One form handles both roles."""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction

from .models import CompanyProfile, SeekerProfile, User


class RegistrationForm(UserCreationForm):
    """
    Creates a User and the profile row matching the chosen role.

    One form rather than one per role: the only difference between the two
    paths is which profile model receives the name, so two forms would be two
    copies of the same four fields.

    `role` is declared here instead of being pulled in through Meta.fields so
    the radio list does not get an empty "---------" option, which Django adds
    to a required model choice field that has no default.

    The password labels and validation messages are not set here -- Django
    ships Arabic translations for them and LANGUAGE_CODE is "ar".
    """

    role = forms.ChoiceField(
        choices=User.Role.choices,
        widget=forms.RadioSelect,
        label="أسجّل بصفتي",
    )
    display_name = forms.CharField(
        max_length=200,
        label="الاسم",
        help_text="اسم الشركة، أو اسمك الكامل إذا كنت باحثًا عن عمل.",
    )

    field_order = ["email", "display_name", "role", "password1", "password2"]

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)

    @transaction.atomic
    def save(self, commit=True):
        """
        Save the user and its profile together.

        Wrapped in a transaction so a failure while creating the profile does
        not leave behind a user with no profile, which every dashboard view
        would then crash on.
        """
        user = super().save(commit=False)
        user.role = self.cleaned_data["role"]
        user.save()

        name = self.cleaned_data["display_name"]
        if user.is_company:
            CompanyProfile.objects.create(user=user, name=name)
        else:
            SeekerProfile.objects.create(user=user, full_name=name)

        return user
