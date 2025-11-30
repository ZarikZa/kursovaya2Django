import random
from django.http import JsonResponse
import requests
from .models import *
from .forms import *
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView
from django.db.models import Q
from django.core.paginator import Paginator
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages

def get_client_ip(request):
    """Получение IP-адреса клиента"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_or_create_action_type(code, name):
    """Получение или создание типа действия"""
    action_type, created = ActionType.objects.get_or_create(
        code=code,
        defaults={'name': name}
    )
    return action_type

def log_user_action(user, action_code, action_name, target_company=None, target_object=None, details="", request=None):
    """
    Логирование действий пользователя
    """
    action_type = get_or_create_action_type(action_code, action_name)
    
    target_object_id = None
    target_content_type = ""
    
    if target_object:
        target_object_id = target_object.id
        target_content_type = target_object.__class__.__name__
    
    ip_address = get_client_ip(request) if request else None
    user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''
    
    AdminLog.objects.create(
        admin=user,
        action=action_type,
        target_company=target_company,
        target_object_id=target_object_id,
        target_content_type=target_content_type,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent
    )

def home_page(request):
    """
    Отображение главной страницы со статистикой
    """
    active_vacancies_count = Vacancy.objects.filter(
        status__status_vacancies_name='Активна'
    ).count()
    
    approved_companies_count = Company.objects.filter(
        status=Company.STATUS_APPROVED
    ).count()
    
    applicants_count = Applicant.objects.count()
    
    successful_responses_count = Response.objects.filter(
        status__status_response_name='Принято'
    ).count()
    
    context = {
        'active_vacancies_count': active_vacancies_count,
        'approved_companies_count': approved_companies_count,
        'applicants_count': applicants_count,
        'successful_responses_count': successful_responses_count,
    }
    
    return render(request, 'home.html', context)

@login_required
def applicant_profile(request):
    """
    Просмотр профиля соискателя
    """
    applicant = get_object_or_404(Applicant, user=request.user)
    
    favorites = Favorites.objects.filter(applicant=applicant).select_related('vacancy')
    responses = Response.objects.filter(applicants=applicant).select_related('vacancy', 'status')
    
    context = {
        'applicant': applicant,
        'favorites': favorites,
        'responses': responses,
    }
    return render(request, 'profile.html', context)

def custom_login(request):
    """
    Кастомный вход в систему с проверкой статуса компании
    """
    if request.user.is_authenticated:
        return redirect('home_page')
    
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('username') 
            password = form.cleaned_data.get('password')
            user = authenticate(request, email=email, password=password)  
            
            if user is not None:
                if hasattr(user, 'company'):
                    company = user.company
                    
                    if company.status == Company.STATUS_PENDING:
                        return redirect('account_pending')
                    elif company.status == Company.STATUS_REJECTED:
                        return render(request, 'auth/login.html', {'form': form})
                
                remember_me = request.POST.get('remember_me')
                if remember_me:
                    request.session.set_expiry(60 * 60 * 24 * 30)  
                else:
                    request.session.set_expiry(0)
                
                login(request, user)
                
                # Логирование входа пользователя
                log_user_action(
                    user=user,
                    action_code='user_login',
                    action_name='Пользователь вошел в систему',
                    details=f'Успешный вход в систему',
                    request=request
                )
                
                next_url = request.GET.get('next')
                if next_url and next_url.startswith('/'):
                    return redirect(next_url)
                else:
                    if hasattr(user, 'company') or hasattr(user, 'hragent'):
                        return redirect('home_comp')
                    else:
                        return redirect('home_page')
            else:
                form.add_error(None, '❌ Неверный email или пароль')
        else:
            print(f"DEBUG: Form errors: {form.errors}")  
    else:
        form = CustomAuthenticationForm()
    
    return render(request, 'auth/login.html', {'form': form})

class ApplicantRegisterView(CreateView):
    """
    Регистрация нового соискателя
    """
    model = User
    form_class = ApplicantSignUpForm
    template_name = 'auth/register.html'
    
    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        
        # Логирование регистрации
        log_user_action(
            user=user,
            action_code='user_registered',
            action_name='Пользователь зарегистрировался',
            details=f'Зарегистрирован новый аккаунт соискателя',
            request=self.request
        )
        
        next_url = self.request.GET.get('next')
        
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        else:
            return redirect('home_page')  
    
    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

def custom_logout(request):
    """
    Выход из системы
    """
    # Логирование выхода
    if request.user.is_authenticated:
        log_user_action(
            user=request.user,
            action_code='user_logout',
            action_name='Пользователь вышел из системы',
            details=f'Выход из системы',
            request=request
        )
    
    logout(request)
    next_url = request.GET.get('next')
        
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    else:
        return redirect('home_page')
    
def vakansii_page(request):
    """
    Отображение списка вакансий с фильтрацией и поиском
    """
    vacancies = Vacancy.objects.select_related(
        'company', 
        'work_conditions', 
        'status'
    ).filter(status__status_vacancies_name='Активна')
    
    search_query = request.GET.get('search', '')
    if search_query:
        vacancies = vacancies.filter(
            Q(position__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(company__name__icontains=search_query)
        )
    
    employment_filters = request.GET.getlist('employment')
    if employment_filters:
        vacancies = vacancies.filter(work_conditions__work_conditions_name__in=employment_filters)
    
    experience_filters = request.GET.getlist('experience')
    if experience_filters:
        vacancies = vacancies.filter(experience__in=experience_filters)
    
    salary_from = request.GET.get('salary_from')
    salary_to = request.GET.get('salary_to')
    if salary_from:
        vacancies = vacancies.filter(salary_min__gte=salary_from)
    if salary_to:
        vacancies = vacancies.filter(salary_max__lte=salary_to)
    
    sort_by = request.GET.get('sort', 'newest')
    if sort_by == 'salary_high':
        vacancies = vacancies.order_by('-salary_max')
    elif sort_by == 'salary_low':
        vacancies = vacancies.order_by('salary_min')
    else: 
        vacancies = vacancies.order_by('-created_date')
    
    paginator = Paginator(vacancies, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    work_conditions = WorkConditions.objects.all()
    selected_employments = request.GET.getlist('employment')
    selected_experiences = request.GET.getlist('experience')
    
    if request.user.is_authenticated and request.user.user_type == 'applicant':
        try:
            applicant = Applicant.objects.get(user=request.user)
            for vacancy in page_obj.object_list:
                vacancy.has_response = vacancy.response_set.filter(applicants=applicant).exists()
        except Applicant.DoesNotExist:
            for vacancy in page_obj.object_list:
                vacancy.has_response = False
    else:
        for vacancy in page_obj.object_list:
            vacancy.has_response = False
    
    context = {
        'page_obj': page_obj,
        'work_conditions': work_conditions,
        'selected_employments': selected_employments,
        'selected_experiences': selected_experiences,
        'salary_from': request.GET.get('salary_from', ''),
        'salary_to': request.GET.get('salary_to', ''),
    }
    return render(request, 'vakans.html', context)

def vacancy_detail(request, vacancy_id):
    """
    Детальное отображение вакансии
    """
    vacancy = get_object_or_404(Vacancy.objects.select_related('company', 'work_conditions', 'status'), id=vacancy_id)
    vacancy.views += 1
    vacancy.save(update_fields=['views'])
    
    # Логирование просмотра вакансии
    if request.user.is_authenticated:
        log_user_action(
            user=request.user,
            action_code='vacancy_viewed',
            action_name='Просмотр вакансии',
            target_object=vacancy,
            target_company=vacancy.company,
            details=f'Просмотр вакансии "{vacancy.position}"',
            request=request
        )
    
    is_favorite = False
    has_response = False
    
    if request.user.is_authenticated and request.user.user_type == 'applicant':
        try:
            applicant = Applicant.objects.get(user=request.user)
            is_favorite = vacancy.favorites_set.filter(applicant=applicant).exists()
            has_response = vacancy.response_set.filter(applicants=applicant).exists()
        except Applicant.DoesNotExist:
            pass 
    
    context = {
        'vacancy': vacancy,
        'is_favorite': is_favorite,
        'has_response': has_response,
    }
    return render(request, 'vacancy_detail.html', context)

def apply_to_vacancy(request, vacancy_id):
    """
    Подача отклика на вакансию
    """
    if not request.user.is_authenticated or request.user.user_type != 'applicant':
        return redirect('vacancy_detail', vacancy_id=vacancy_id)
    
    vacancy = get_object_or_404(Vacancy, id=vacancy_id)
    
    try:
        applicant = Applicant.objects.get(user=request.user)
    except Applicant.DoesNotExist:
        return redirect('vacancy_detail', vacancy_id=vacancy_id)
    
    existing_response = Response.objects.filter(
        applicants=applicant, 
        vacancy=vacancy
    ).exists()
    
    if existing_response:
        return redirect('vacancy_detail', vacancy_id=vacancy_id)
    
    try:
        status_new, created = StatusResponse.objects.get_or_create(
            status_response_name='Новый',
            defaults={'status_response_name': 'Новый'}
        )
        
        response = Response.objects.create(
            applicants=applicant,
            vacancy=vacancy,
            status=status_new
        )
        
        # Логирование отклика на вакансию
        log_user_action(
            user=request.user,
            action_code='vacancy_applied',
            action_name='Отклик на вакансию',
            target_object=vacancy,
            target_company=vacancy.company,
            details=f'Отклик на вакансию "{vacancy.position}" в компании {vacancy.company.name}',
            request=request
        )
        
    except Exception as e:
        pass
    return redirect('vakansi_page')

@login_required
def add_to_favorites(request, vacancy_id):
    """
    Добавление вакансии в избранное
    """
    if request.user.user_type != 'applicant':
        return redirect('vacancy_detail', vacancy_id=vacancy_id)
    
    try:
        applicant = Applicant.objects.get(user=request.user)
        vacancy = get_object_or_404(Vacancy, id=vacancy_id)
        
        favorite_exists = Favorites.objects.filter(
            applicant=applicant, 
            vacancy=vacancy
        ).exists()
        
        if favorite_exists:
            pass
        else:
            Favorites.objects.create(applicant=applicant, vacancy=vacancy)
            
            # Логирование добавления в избранное
            log_user_action(
                user=request.user,
                action_code='favorite_added',
                action_name='Добавлено в избранное',
                target_object=vacancy,
                target_company=vacancy.company,
                details=f'Вакансия "{vacancy.position}" добавлена в избранное',
                request=request
            )
            
    except Applicant.DoesNotExist:
        pass
    
    return redirect('vacancy_detail', vacancy_id=vacancy_id)

@login_required
def remove_from_favorites(request, vacancy_id):
    """
    Удаление вакансии из избранного
    """
    if request.user.user_type != 'applicant':
        return redirect('vacancy_detail', vacancy_id=vacancy_id)
    
    try:
        applicant = Applicant.objects.get(user=request.user)
        vacancy = get_object_or_404(Vacancy, id=vacancy_id)
        
        favorite = Favorites.objects.filter(
            applicant=applicant, 
            vacancy=vacancy
        ).first()
        
        if favorite:
            favorite.delete()
            
            # Логирование удаления из избранного
            log_user_action(
                user=request.user,
                action_code='favorite_removed',
                action_name='Удалено из избранного',
                target_object=vacancy,
                target_company=vacancy.company,
                details=f'Вакансия "{vacancy.position}" удалена из избранного',
                request=request
            )
       
    except Applicant.DoesNotExist:
        pass
    
    return redirect('vacancy_detail', vacancy_id=vacancy_id)

@login_required
def edit_applicant_profile(request):
    """
    Редактирование профиля соискателя
    """
    if request.user.user_type != 'applicant':
        return redirect('home_page')
    
    applicant = get_object_or_404(Applicant, user=request.user)
    
    if request.method == 'POST':
        form = ApplicantEditForm(request.POST, instance=applicant)
        user_form = UserEditForm(request.POST, instance=request.user)
        
        if form.is_valid() and user_form.is_valid():
            form.save()
            user_form.save()
            
            # Логирование обновления профиля
            log_user_action(
                user=request.user,
                action_code='profile_updated',
                action_name='Профиль обновлен',
                details='Профиль соискателя обновлен',
                request=request
            )
            
            return redirect('applicant_profile')
    else:
        form = ApplicantEditForm(instance=applicant)
        user_form = UserEditForm(instance=request.user)
    
    context = {
        'form': form,
        'user_form': user_form,
    }
    return render(request, 'edit_applicant_profile.html', context)

@login_required
def delete_applicant_profile(request):
    """
    Удаление профиля соискателя
    """
    if request.user.user_type != 'applicant':
        return redirect('home_page')
    
    if request.method == 'POST':
        user = request.user
        
        # Логирование удаления профиля
        log_user_action(
            user=user,
            action_code='profile_deleted',
            action_name='Профиль удален',
            details='Профиль соискателя удален',
            request=request
        )
        
        user.delete()
        return redirect('home_page')
    
    return redirect('applicant_profile')

User = get_user_model()

def password_reset_request(request):
    """
    Запрос сброса пароля
    """
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            
            try:
                user = User.objects.get(email=email)
                reset_code = str(random.randint(100000, 999999))
                
                request.session['reset_email'] = email
                request.session['reset_code'] = reset_code
                request.session['reset_attempts'] = 3
                
                send_reset_code_email(user, reset_code)
                
                # Логирование запроса сброса пароля
                log_user_action(
                    user=user,
                    action_code='password_reset_requested',
                    action_name='Запрос сброса пароля',
                    details='Запрос сброса пароля',
                    request=request
                )
                
                return redirect('password_reset_verify')
                
            except User.DoesNotExist:
                messages.error(request, 'Пользователь с таким email не найден.')
    
    else:
        form = PasswordResetRequestForm()
    
    return render(request, 'password_reset_request.html', {'form': form})

def password_reset_verify(request):
    """
    Подтверждение кода сброса пароля
    """
    if 'reset_email' not in request.session:
        messages.error(request, 'Сначала введите ваш email.')
        return redirect('password_reset_request')
    
    if request.method == 'POST':
        form = CodeVerificationForm(request.POST)
        if form.is_valid():
            entered_code = form.cleaned_data['code']
            correct_code = request.session.get('reset_code')
            attempts = request.session.get('reset_attempts', 3)
            
            if entered_code == correct_code:
                request.session['code_verified'] = True
                return redirect('password_reset_new')
            else:
                attempts -= 1
                request.session['reset_attempts'] = attempts
                
                if attempts <= 0:
                    del request.session['reset_email']
                    del request.session['reset_code']
                    del request.session['reset_attempts']
                    messages.error(request, 'Превышено количество попыток. Начните заново.')
                    return redirect('password_reset_request')
                else:
                    messages.error(request, f'Неверный код. Осталось попыток: {attempts}')
    
    else:
        form = CodeVerificationForm()
    
    return render(request, 'password_reset_verify.html', {
        'form': form,
        'email': request.session.get('reset_email'),
        'attempts': request.session.get('reset_attempts', 3)
    })

def password_reset_new(request):
    """
    Установка нового пароля
    """
    if not request.session.get('code_verified'):
        messages.error(request, 'Сначала подтвердите ваш email.')
        return redirect('password_reset_request')
    
    if request.method == 'POST':
        form = SetNewPasswordForm(request.POST)
        if form.is_valid():
            email = request.session.get('reset_email')
            
            try:
                user = User.objects.get(email=email)
                new_password = form.cleaned_data['new_password1']
                user.set_password(new_password)
                user.save()
                
                # Логирование успешного сброса пароля
                log_user_action(
                    user=user,
                    action_code='password_reset_success',
                    action_name='Пароль успешно сброшен',
                    details='Пароль успешно сброшен',
                    request=request
                )
                
                request.session.flush()
                
                messages.success(request, 'Пароль успешно изменен! Теперь вы можете войти с новым паролем.')
                if user.is_authenticated:
                    match user.user_type:
                        case "applicant":
                            return redirect('applicant_profile')
                        case "compani":
                            return redirect('company_profile')
                        case "hragent":
                            return redirect('employee_profile')
                if user.user_type == "applicant":
                    return redirect('login_user')

            except User.DoesNotExist:
                messages.error(request, 'Ошибка. Пользователь не найден.')
                return redirect('password_reset_request')
    else:
        form = SetNewPasswordForm()
    
    return render(request, 'password_reset_new.html', {'form': form})

def send_reset_code_email(user, code):
    """
    Отправка кода сброса пароля по email
    """
    user_email = user.email
    first_name = user.first_name or 'Пользователь'
    
    try:
        subject = f'Код восстановления пароля: {code}'
        
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Inter', 'Arial', sans-serif;
                    line-height: 1.6;
                    color: #1e293b;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 0;
                    background: linear-gradient(135deg, #2563eb 0%, #1e293b 100%);
                }}
                .container {{
                    background: white;
                    margin: 20px;
                    border-radius: 20px;
                    overflow: hidden;
                    box-shadow: 0 15px 35px rgba(0, 0, 0, 0.2);
                }}
                .header {{
                    background: linear-gradient(135deg, #2563eb 0%, #1e293b 100%);
                    color: white;
                    padding: 40px 30px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                    font-weight: 700;
                }}
                .content {{
                    padding: 40px 30px;
                }}
                .code-section {{
                    text-align: center;
                    margin: 30px 0;
                }}
                .code {{
                    background: linear-gradient(45deg, #2563eb, #1e40af);
                    color: white;
                    font-size: 32px;
                    font-weight: bold;
                    padding: 20px;
                    border-radius: 15px;
                    letter-spacing: 8px;
                    margin: 20px 0;
                    display: inline-block;
                    min-width: 200px;
                }}
                .security-note {{
                    background: rgba(245, 158, 11, 0.1);
                    border: 1px solid rgba(245, 158, 11, 0.3);
                    border-radius: 10px;
                    padding: 15px;
                    margin: 20px 0;
                    text-align: center;
                    font-size: 14px;
                    color: #92400e;
                }}
                .footer {{
                    background: #f1f5f9;
                    padding: 30px;
                    text-align: center;
                    border-top: 1px solid #e2e8f0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>HR-Lab</h1>
                    <p>Восстановление пароля</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #1e293b; text-align: center;">Здравствуйте, {first_name}!</h2>
                    <p style="color: #64748b; text-align: center;">
                        Для восстановления пароля используйте следующий код:
                    </p>
                    
                    <div class="code-section">
                        <div class="code">{code}</div>
                        <p style="color: #64748b; font-size: 14px;">
                            Код действителен в течение 10 минут
                        </p>
                    </div>
                    
                    <div class="security-note">
                        ⚠️ <strong>Никому не сообщайте этот код!</strong><br>
                        Если вы не запрашивали восстановление пароля, проигнорируйте это письмо.
                    </div>
                </div>
                
                <div class="footer">
                    <p><strong>С уважением, команда HR-Lab</strong></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_message = f"""
        Здравствуйте, {first_name}!

        Код для восстановления пароля: {code}

        Код действителен в течение 10 минут.

        ⚠️ Никому не сообщайте этот код!

        Если вы не запрашивали восстановление пароля, проигнорируйте это письмо.

        ---
        С уважением,
        Команда HR-Lab
        """
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=False,
        )
        
        print(f"✅ [EMAIL] Код восстановления отправлен: {user_email} - {code}")
        return True
        
    except Exception as e:
        print(f"❌ [EMAIL] Ошибка отправки кода: {str(e)}")
        return False

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json

@require_POST
@csrf_exempt
def update_theme(request):
    """
    Обновление темы для авторизованного пользователя
    """
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'User not authenticated'})
    
    try:
        data = json.loads(request.body)
        theme = data.get('theme')
        
        print(f"Updating theme for user {request.user.username} to {theme}")
        
        if theme not in ['light', 'dark']:
            return JsonResponse({'status': 'error', 'message': 'Invalid theme'})
        
        user = request.user
        
        if hasattr(user, 'applicant'):
            user.applicant.theme = theme
            user.applicant.save()
            user_type = 'applicant'
            print(f"Theme updated for applicant: {theme}")
            
        elif hasattr(user, 'employee'):
            user.employee.theme = theme
            user.employee.save()
            user_type = 'employee'
            print(f"Theme updated for employee: {theme}")
            
        elif hasattr(user, 'company'):
            user.company.theme = theme
            user.company.save()
            user_type = 'company'
            print(f"Theme updated for company: {theme}")
            
        else:
            return JsonResponse({'status': 'error', 'message': 'User type not found'})
        
        # Логирование изменения темы
        log_user_action(
            user=user,
            action_code='theme_changed',
            action_name='Тема изменена',
            details=f'Тема изменена на: {theme}',
            request=request
        )
        
        return JsonResponse({
            'status': 'success', 
            'message': f'Theme updated for {user_type}',
            'theme': theme,
            'user_type': user_type
        })
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'})
    except Exception as e:
        print(f"Error updating theme: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)})

@login_required
def create_complaint(request, vacancy_id):
    """
    Создание жалобы на вакансию
    """
    vacancy = get_object_or_404(Vacancy, id=vacancy_id)
    
    existing_complaint = Complaint.objects.filter(
        vacancy=vacancy, 
        complainant=request.user
    ).first()
    
    if existing_complaint:
        messages.warning(request, f'Вы уже подавали жалобу на эту вакансию. Статус: {existing_complaint.get_status_display()}')
        return redirect('vacancy_detail', vacancy_id=vacancy_id)
    
    if request.method == 'POST':
        form = ComplaintForm(request.POST)
        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.vacancy = vacancy
            complaint.complainant = request.user
            complaint.save()
            
            # Логирование создания жалобы
            log_user_action(
                user=request.user,
                action_code='complaint_created',
                action_name='Создана жалоба',
                target_object=vacancy,
                target_company=vacancy.company,
                details=f'Создана жалоба на вакансию "{vacancy.position}"',
                request=request
            )
            
            messages.success(request, 'Жалоба успешно отправлена на рассмотрение.')
            return redirect('vacancy_detail', vacancy_id=vacancy_id)
    else:
        form = ComplaintForm()
    
    return render(request, 'complaints/create_complaint.html', {
        'form': form,
        'vacancy': vacancy
    })

@login_required
def complaint_success(request, vacancy_id):
    """
    Страница успешной отправки жалобы
    """
    vacancy = get_object_or_404(Vacancy, id=vacancy_id)
    return render(request, 'complaints/complaint_success.html', {'vacancy': vacancy})

@login_required
def check_existing_complaint(request, vacancy_id):
    """
    Проверка существующей жалобы (AJAX)
    """
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        vacancy = get_object_or_404(Vacancy, id=vacancy_id)
        existing_complaint = Complaint.objects.filter(
            vacancy=vacancy, 
            complainant=request.user
        ).first()
        
        if existing_complaint:
            return JsonResponse({
                'exists': True,
                'status': existing_complaint.get_status_display(),
                'type': existing_complaint.get_complaint_type_display()
            })
        return JsonResponse({'exists': False})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .influxdb_metrics import InfluxDBSender

@csrf_exempt
def send_metrics(request):
    """
    Отправка метрик в InfluxDB
    """
    if request.method == 'GET':
        try:
            sender = InfluxDBSender()
            results = sender.send_all_metrics()
            
            # Логирование отправки метрик
            if request.user.is_authenticated:
                log_user_action(
                    user=request.user,
                    action_code='metrics_sent',
                    action_name='Метрики отправлены',
                    details='Отправка метрик в InfluxDB',
                    request=request
                )
            
            return JsonResponse({
                'status': 'ура',
                'message': 'Метрики отправлены',
                'results': results
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'ошибка',
                'message': str(e)
            }, status=500)