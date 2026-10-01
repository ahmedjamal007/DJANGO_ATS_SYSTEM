"""Job create/edit form, and the listing filter form."""

from django import forms

from .models import Job


class JobForm(forms.ModelForm):
    """
    The company-facing job form.

    `company` is not a field. It is taken from the logged-in user in the view,
    so a hand-crafted POST cannot assign a job to somebody else's company.
    """

    class Meta:
        model = Job
        fields = [
            "title",
            "description",
            "required_skills",
            "location",
            "employment_type",
            "salary_min",
            "salary_max",
            "status",
        ]
        widgets = {
            # Job text and skill phrases are written in English on an Arabic
            # page, so these three controls are forced left-to-right.
            "title": forms.TextInput(attrs={"dir": "ltr"}),
            "description": forms.Textarea(attrs={"rows": 8, "dir": "ltr"}),
            "required_skills": forms.Textarea(
                attrs={
                    "rows": 6,
                    "dir": "ltr",
                    "placeholder": (
                        "building single-page apps with React and Redux\n"
                        "designing and documenting REST APIs with Django\n"
                        "optimising slow PostgreSQL queries"
                    ),
                }
            ),
        }

    def clean_required_skills(self):
        """At least one usable skill line, or Phase 5 has nothing to score."""
        raw = self.cleaned_data["required_skills"]
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:
            raise forms.ValidationError("أضف مهارة واحدة على الأقل.")
        # Store back normalised, so skill_lines() and the stored text agree.
        return "\n".join(lines)

    def clean(self):
        """Model-level range check, surfaced on the form."""
        cleaned = super().clean()
        low, high = cleaned.get("salary_min"), cleaned.get("salary_max")
        if low is not None and high is not None and high < low:
            self.add_error(
                "salary_max", "أعلى راتب يجب أن يكون مساويًا لأقل راتب أو أكبر منه."
            )
        return cleaned


class JobFilterForm(forms.Form):
    """Filters on the public listing. Every field is optional."""

    q = forms.CharField(
        required=False,
        label="بحث",
        widget=forms.TextInput(attrs={"placeholder": "المسمى الوظيفي أو اسم الشركة"}),
    )
    location = forms.CharField(
        required=False,
        label="المدينة",
        widget=forms.TextInput(attrs={"placeholder": "الخرطوم"}),
    )
    employment_type = forms.ChoiceField(
        required=False,
        label="نوع التوظيف",
        choices=[("", "الكل")] + list(Job.EmploymentType.choices),
    )
