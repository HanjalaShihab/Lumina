from django import forms

from .models import EnhancementJob


class ImageUploadForm(forms.ModelForm):
    class Meta:
        model = EnhancementJob
        fields = ["title", "original"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Optional image title"}),
            "original": forms.FileInput(attrs={"accept": "image/*"}),
        }


class BackgroundRemovalForm(forms.ModelForm):
    class Meta:
        model = EnhancementJob
        fields = ["title", "original"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Optional image title"}),
            "original": forms.FileInput(attrs={"accept": "image/*"}),
        }


class ManualEnhancementForm(forms.ModelForm):
    class Meta:
        model = EnhancementJob
        fields = ["title", "original"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Optional image title"}),
            "original": forms.FileInput(attrs={"accept": "image/*"}),
        }


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return single_file_clean(data, initial)


class BatchEnhancementForm(forms.Form):
    images = MultipleFileField(
        widget=MultipleFileInput(attrs={"accept": "image/*", "multiple": True}),
        label="Images",
    )
