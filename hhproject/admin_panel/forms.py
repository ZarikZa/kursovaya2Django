from django import forms
from home.models import Company, Employee, User

class CompanyModerationForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={
                'class': 'form-control',
            })
        }


class BackupUploadForm(forms.Form):
    backup_file = forms.FileField(
        label='Файл бэкапа',
        help_text='Поддерживаемые форматы: .zip, .json',
        widget=forms.FileInput(attrs={
            'accept': '.zip,.json',
            'class': 'file-input'
        })
    )

class SiteAdminCreateForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=80,
        required=True,
        label="Имя",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите имя',
            'autocomplete': 'given-name'
        })
    )
    last_name = forms.CharField(
        max_length=80,
        required=True,
        label="Фамилия",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите фамилию',
            'autocomplete': 'family-name'
        })
    )
    email = forms.EmailField(
        required=True,
        label="Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@email.com',
            'autocomplete': 'email'
        })
    )
    phone = forms.CharField(
        max_length=80,
        required=True,
        label="Телефон",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+7 (999) 999-99-99',
            'autocomplete': 'tel'
        })
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Не менее 8 символов',
            'autocomplete': 'new-password'
        }),
        label="Пароль"
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Повторите пароль',
            'autocomplete': 'new-password'
        }),
        label="Подтверждение пароля"
    )

    class Meta:
        model = User
        fields = ['email', 'phone', 'first_name', 'last_name']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Пользователь с таким email уже существует')
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Пароли не совпадают')
        return password2

    def save(self, commit=True):
        # Создаем пользователя
        user = User.objects.create_user(
            username=self.cleaned_data['email'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password1'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            phone=self.cleaned_data['phone'],
            user_type='adminsite',
            is_active=True
        )

        # Создаем запись Employee с корректными полями
        employee = Employee.objects.create(
            user=user,
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            access_level='admin'
            # company, theme - оставляем пустыми или с дефолтными значениями
        )
        
        return user
class SiteAdminEditForm(forms.ModelForm):
    email = forms.EmailField(
        required=True,
        label="Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@email.com'
        })
    )
    phone = forms.CharField(
        max_length=80,
        required=True,
        label="Телефон",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+7 (999) 999-99-99'
        })
    )
    first_name = forms.CharField(
        max_length=80,
        required=True,
        label="Имя",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите имя'
        })
    )
    last_name = forms.CharField(
        max_length=80,
        required=True,
        label="Фамилия",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите фамилию'
        })
    )
    is_active = forms.BooleanField(
        required=False,
        label="Активен",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

    class Meta:
        model = Employee
        fields = ['first_name', 'last_name', 'access_level']  # Добавьте access_level

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['email'].initial = self.instance.user.email
            self.fields['phone'].initial = self.instance.user.phone
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['is_active'].initial = self.instance.user.is_active

    def save(self, commit=True):
        employee = super().save(commit=False)
        if employee.user:
            employee.user.email = self.cleaned_data['email']
            employee.user.phone = self.cleaned_data['phone']
            employee.user.first_name = self.cleaned_data['first_name']
            employee.user.last_name = self.cleaned_data['last_name']
            employee.user.is_active = self.cleaned_data['is_active']
            if commit:
                employee.user.save()
                employee.save()
        return employee
from django.contrib.auth.forms import UserChangeForm

class AdminProfileEditForm(UserChangeForm):
    phone = forms.CharField(
        max_length=80,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Введите номер телефона'
        }),
        label='Телефон'
    )
    
    first_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Введите имя'
        }),
        label='Имя'
    )
    
    last_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Введите фамилию'
        }),
        label='Фамилия'
    )

    class Meta:
        model = User
        fields = ['email', 'phone', 'first_name', 'last_name']
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'Введите email'
            }),
        }
    
