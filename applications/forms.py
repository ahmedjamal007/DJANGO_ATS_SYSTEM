"""Resume upload form. All file validation happens here."""

import os

from django import forms
from django.conf import settings
from django.template.defaultfilters import filesizeformat

from .models import Application, RecruiterNote, Resume


class ResumeUploadForm(forms.ModelForm):
    class Meta:
        model = Resume
        fields = ["file"]
        # `accept` only filters the file picker; it is a convenience, not a
        # control. The real check is clean_file() below, which runs on the
        # server and cannot be bypassed by editing the page.
        widgets = {"file": forms.ClearableFileInput(attrs={"accept": ".pdf,.docx"})}
        labels = {"file": "ملف السيرة الذاتية"}
        help_texts = {
            "file": "صيغة PDF أو DOCX فقط، بحد أقصى 5 ميجابايت. يُفضَّل أن تكون السيرة بالإنجليزية."
        }

    def clean_file(self):
        """
        Reject anything we cannot read, before it is saved.

        Checked here rather than in the view so the message appears next to the
        field, and so the file never reaches the parser in the first place.
        """
        uploaded = self.cleaned_data["file"]

        extension = os.path.splitext(uploaded.name)[1].lower()
        allowed = settings.RESUME_ALLOWED_EXTENSIONS
        if extension not in allowed:
            raise forms.ValidationError(
                "صيغة غير مدعومة. الصيغ المقبولة: %(allowed)s",
                params={"allowed": "، ".join(allowed)},
            )

        if uploaded.size > settings.RESUME_MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                "حجم الملف %(size)s ويتجاوز الحد الأقصى %(limit)s.",
                params={
                    "size": filesizeformat(uploaded.size),
                    "limit": filesizeformat(settings.RESUME_MAX_UPLOAD_BYTES),
                },
            )

        if uploaded.size == 0:
            raise forms.ValidationError("الملف فارغ.")

        return uploaded


class ApplyForm(forms.Form):
    """Cover letter only. The resume is the seeker's active one, not a choice."""

    cover_letter = forms.CharField(
        label="رسالة التقديم",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 6,
                "dir": "ltr",
                "placeholder": "Optional. Tell the company why you are a good fit.",
            }
        ),
        help_text="اختيارية. تُقرأ من قِبل الشركة ولا تدخل في حساب النتيجة.",
    )


class RecruiterNoteForm(forms.ModelForm):
    class Meta:
        model = RecruiterNote
        fields = ["body", "rating"]
        labels = {"body": "ملاحظة", "rating": "التقييم"}
        widgets = {
            "body": forms.Textarea(
                attrs={"rows": 3, "placeholder": "ملاحظتك عن هذا المتقدم…"}
            )
        }
