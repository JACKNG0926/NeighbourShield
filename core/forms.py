from django import forms

from .models import Area, Property, SafetyPost

INPUT_CLASS = 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-600 focus:ring-blue-600'


class AreaRegistrationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ('center_latitude', 'center_longitude', 'radius_m'):
            self.fields[field_name].required = True

    class Meta:
        model = Area
        fields = ('name', 'center_latitude', 'center_longitude', 'radius_m')
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g. Precinct A'}),
            'center_latitude': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.000001', 'placeholder': '3.139000'}),
            'center_longitude': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.000001', 'placeholder': '101.686900'}),
            'radius_m': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': '1', 'placeholder': '500'}),
        }


class PropertyRegistrationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ('latitude', 'longitude'):
            self.fields[field_name].required = True

    class Meta:
        model = Property
        fields = ('area', 'unit_number', 'address_line', 'postal_code', 'property_type',
                  'latitude', 'longitude')
        widgets = {
            'area': forms.Select(attrs={'class': INPUT_CLASS}),
            'unit_number': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g. A-12-03'}),
            'address_line': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Street and neighbourhood'}),
            'postal_code': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g. 50000'}),
            'property_type': forms.Select(attrs={'class': INPUT_CLASS}),
            'latitude': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.000001'}),
            'longitude': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.000001'}),
        }

class BroadcastForm(forms.ModelForm):
    affected_areas = forms.ModelMultipleChoiceField(
        queryset=Area.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'mr-2'}),
        required=False,
        help_text="Leave blank to notify the entire township."
    )

    class Meta:
        model = SafetyPost
        fields = ['category', 'severity', 'title', 'description', 'affected_areas']
        widgets = {
            'category': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm'}),
            'severity': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm'}),
            'title': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm p-2 border'}),
            'description': forms.Textarea(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm p-2 border', 'rows': 3}),
        }
