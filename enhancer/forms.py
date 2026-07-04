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


class ManualEnhancementForm(forms.ModelForm):
    brightness = forms.FloatField(min_value=0.2, max_value=2.5, initial=1.08)
    contrast = forms.FloatField(min_value=0.2, max_value=2.5, initial=1.12)
    sharpness = forms.FloatField(min_value=0.2, max_value=3.0, initial=1.25)
    saturation = forms.FloatField(min_value=0.0, max_value=2.5, initial=1.08)

    class Meta:
        model = EnhancementJob
        fields = ["title", "original", "brightness", "contrast", "sharpness", "saturation"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Optional image title"}),
            "original": forms.FileInput(attrs={"accept": "image/*"}),
            "brightness": forms.NumberInput(attrs={"step": "0.01"}),
            "contrast": forms.NumberInput(attrs={"step": "0.01"}),
            "sharpness": forms.NumberInput(attrs={"step": "0.01"}),
            "saturation": forms.NumberInput(attrs={"step": "0.01"}),
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
