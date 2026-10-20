import re
from django import forms
from .models import Area, Property, SafetyPost

INPUT_CLASS = 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-600 focus:ring-blue-600'


class AreaRegistrationForm(forms.ModelForm):
    class Meta:
        model = Area
        fields = ('name', 'center_latitude', 'center_longitude', 'radius_m')
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g. Precinct A'}),
            'center_latitude': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.000001', 'placeholder': '3.139000'}),
            'center_longitude': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.000001', 'placeholder': '101.686900'}),
            'radius_m': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': '10', 'placeholder': '500'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ('name', 'center_latitude', 'center_longitude', 'radius_m'):
            self.fields[f].required = True

    def clean_name(self):
        name = (self.cleaned_data['name'] or '').strip()
        if len(name) < 2:
            raise forms.ValidationError('Area name must be at least 2 characters.')
        return name

    def clean_center_latitude(self):
        v = self.cleaned_data['center_latitude']
        if v is None or not (-90 <= float(v) <= 90):
            raise forms.ValidationError('Latitude must be between -90 and 90.')
        return v

    def clean_center_longitude(self):
        v = self.cleaned_data['center_longitude']
        if v is None or not (-180 <= float(v) <= 180):
            raise forms.ValidationError('Longitude must be between -180 and 180.')
        return v

    def clean_radius_m(self):
        v = self.cleaned_data['radius_m']
        if v is None or v < 10:
            raise forms.ValidationError('Radius must be at least 10 m.')
        if v > 20000:
            raise forms.ValidationError('Radius looks too large (max 20 km).')
        return v


class PropertyRegistrationForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = ('area', 'unit_number', 'address_line', 'postal_code', 'property_type', 'latitude', 'longitude')
        widgets = {
            'area': forms.Select(attrs={'class': INPUT_CLASS}),
            'unit_number': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g. A-12-03'}),
            'address_line': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g. Jalan Bunga Raya'}),
            'postal_code': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g. 50000'}),
            'property_type': forms.Select(attrs={'class': INPUT_CLASS}),
            'latitude': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.000001'}),
            'longitude': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.000001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ('area', 'unit_number', 'address_line', 'latitude', 'longitude'):
            self.fields[f].required = True

    def clean_unit_number(self):
        v = (self.cleaned_data['unit_number'] or '').strip().upper()
        if not re.match(r'^[A-Z0-9][A-Z0-9\-/]{1,19}$', v):
            raise forms.ValidationError(
                'Unit number must be 2–20 characters, letters/digits, dash or slash '
                '(e.g. A-12-03).'
            )
        return v

    def clean_postal_code(self):
        v = (self.cleaned_data['postal_code'] or '').strip()
        if v and not re.match(r'^\d{4,6}$', v):
            raise forms.ValidationError('Postal code must be 4–6 digits.')
        return v

    def clean_latitude(self):
        v = self.cleaned_data['latitude']
        if v is None or not (-90 <= float(v) <= 90):
            raise forms.ValidationError('Latitude must be between -90 and 90.')
        return v

    def clean_longitude(self):
        v = self.cleaned_data['longitude']
        if v is None or not (-180 <= float(v) <= 180):
            raise forms.ValidationError('Longitude must be between -180 and 180.')
        return v

    def clean(self):
        cleaned = super().clean()
        area = cleaned.get('area')
        lat = cleaned.get('latitude')
        lng = cleaned.get('longitude')

        # Keep the boundary check so you can't put a property outside the circle
        if area and lat is not None and lng is not None:
            if area.has_boundary:
                distance = area.distance_to(lat, lng)
                if distance > area.radius_m:
                    raise forms.ValidationError(
                        f'Rejected: ({lat:.6f}, {lng:.6f}) is '
                        f'{distance/1000:.2f} km from the centre of "{area.name}", '
                        f'but the allowed radius is {area.radius_m} m.'
                    )
            else:
                self._boundary_warning = f'Area "{area.name}" has no boundary configured.'
        return cleaned


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