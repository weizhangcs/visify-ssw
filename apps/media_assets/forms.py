# apps/media_assets/forms.py
from django import forms
from .models import Media

class MediaAdminForm(forms.ModelForm):
    class Meta:
        model = Media
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }