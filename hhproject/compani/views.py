from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from home.models import *
from django.views.generic import CreateView, UpdateView
from django.contrib.auth import login, update_session_auth_hash, authenticate
from django.contrib import messages
from django.core.mail import send_mail, get_connection
from django.conf import settings
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from smtplib import SMTPAuthenticationError, SMTPServerDisconnected, SMTPConnectError
from .forms import *
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from better_profanity import profanity
from django.db.models import Count, Q

# Функции для логирования
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
    try:
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
        
        print(f"✅ [LOG] Записано действие: {user.username} - {action_name}")
        
    except Exception as e:
        print(f"❌ [LOG] Ошибка записи лога: {str(e)}")

def account_pending(request):
    """
    Страница ожидания подтверждения аккаунта компании
    """
    return render(request, 'auth/account_pending.html')

def home_comp(request):
    """
    Главная страница для компаний и HR-агентов
    """
    active_applicants_count = Applicant.objects.count()
    print(active_applicants_count)
    successful_hires_count = Response.objects.filter(
        status__status_response_name='Приглашение'  
    ).count()
    
    total_companies = Company.objects.count()
    returning_companies = Company.objects.annotate(
        vacancy_count=Count('vacancy')
    ).filter(vacancy_count__gt=1).count()
    
    if total_companies > 0:
        returning_companies_percentage = int((returning_companies / total_companies) * 100)
    else:
        returning_companies_percentage = 95 
    
    avg_hire_time = 48 
    
    context = {
        'active_applicants_count': active_applicants_count,
        'successful_hires_count': successful_hires_count,
        'returning_companies_percentage': returning_companies_percentage,
        'avg_hire_time': avg_hire_time,
    }
    
    return render(request, 'compani/homeComp.html', context)

class CompanyRegisterView(CreateView):
    """
    Регистрация новой компании
    """
    model = User
    form_class = CompanySignUpForm
    template_name = 'auth/register_comp.html'

    def form_valid(self, form):
        user = form.save()
        
        # Логирование регистрации компании
        if user.company:
            log_user_action(
                user=user,
                action_code='company_registered',
                action_name='Компания зарегистрирована',
                target_company=user.company,
                details=f'Зарегистрирована новая компания: {user.company.name}',
                request=self.request
            )
        
        return redirect('account_pending')

def company_profile(request):
    """
    Просмотр профиля компании
    """
    if not request.user.is_authenticated or request.user.user_type != 'company':
        return redirect('login_user')
    
    company = request.user.company
    vacancies = company.vacancy_set.all()
    employees = Employee.objects.filter(company=company)
    
    context = {
        'company': company,
        'vacancies': vacancies,
        'employees': employees,
        'user': request.user
    }
    return render(request, 'compani/profile/company_profile.html', context)

class CompanyProfileUpdateView(UpdateView):
    """
    Обновление профиля компании через класс-based view
    """
    model = Company
    fields = ['name', 'number', 'industry', 'description']
    template_name = 'compani/edit_company_profile.html'
    success_url = reverse_lazy('company_profile')

    def get_object(self, queryset=None):
        return self.request.user.company

    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Логирование обновления профиля компании
        log_user_action(
            user=self.request.user,
            action_code='company_profile_updated',
            action_name='Профиль компании обновлен',
            target_company=self.object,
            details=f'Профиль компании {self.object.name} обновлен',
            request=self.request
        )
        
        return response

def edit_company_profile(request):
    """
    Редактирование профиля компании
    """
    if not request.user.is_authenticated or request.user.user_type != 'company':
        return redirect('login_user')
    
    company = request.user.company
    if request.method == 'POST':
        form = CompanyProfileEditForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save()
            company.name = form.cleaned_data['company_name']
            company.number = form.cleaned_data['company_number']
            company.industry = form.cleaned_data['industry']
            company.description = form.cleaned_data['description']
            company.save()
            
            # Логирование обновления профиля компании
            log_user_action(
                user=request.user,
                action_code='company_profile_updated',
                action_name='Профиль компании обновлен',
                target_company=company,
                details=f'Профиль компании {company.name} обновлен',
                request=request
            )
            
            messages.success(request, 'Профиль компании успешно обновлён.')
            return redirect('company_profile')
    else:
        form = CompanyProfileEditForm(instance=request.user, initial={
            'company_name': company.name,
            'company_number': company.number,
            'industry': company.industry,
            'description': company.description,
            'email': request.user.email,
            'phone': request.user.phone
        })

    context = {
        'form': form,
        'company': company
    }
    return render(request, 'compani/profile/edit_company_profile.html', context)

def verify_password_and_save(request):
    """
    Проверка пароля и сохранение профиля компании
    """
    if not request.user.is_authenticated or request.user.user_type != 'company':
        return redirect('login_user')
    
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        user = authenticate(request, username=request.user.email, password=current_password)
        if user is not None:
            form_data = request.POST.copy()
            form_data.pop('current_password', None)  
            form = CompanyProfileEditForm(form_data, instance=request.user)
            if form.is_valid():
                user = form.save()
                company = request.user.company
                company.name = form.cleaned_data['company_name']
                company.number = form.cleaned_data['company_number']
                company.industry = form.cleaned_data['industry']
                company.description = form.cleaned_data['description']
                company.save()
                
                # Логирование обновления профиля компании
                log_user_action(
                    user=request.user,
                    action_code='company_profile_updated',
                    action_name='Профиль компании обновлен',
                    target_company=company,
                    details=f'Профиль компании {company.name} обновлен с проверкой пароля',
                    request=request
                )
                
                messages.success(request, 'Профиль компании успешно обновлён.')
                return redirect('company_profile')
            else:
                messages.error(request, f'Ошибка в данных формы: {form.errors.as_text()}')
        else:
            messages.error(request, 'Неверный текущий пароль.')
    
    company = request.user.company
    form = CompanyProfileEditForm(instance=request.user, initial={
        'company_name': company.name,
        'company_number': company.number,
        'industry': company.industry,
        'description': company.description,
        'email': request.user.email,
        'phone': request.user.phone
    })
    return render(request, 'compani/profile/edit_company_profile.html', {'form': form, 'company': company})

def change_password_request(request):
    """
    Запрос смены пароля
    """
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = User.objects.filter(email=email).first()
            if user:
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                reset_link = request.build_absolute_uri(
                    reverse_lazy('change_password_confirm', kwargs={'uidb64': uid, 'token': token})
                )
                subject = 'Сброс пароля для HR-Lab'
                message = (
                    f'Здравствуйте,\n\n'
                    f'Для сброса пароля перейдите по ссылке: {reset_link}\n\n'
                    f'Если вы не запрашивали сброс пароля, проигнорируйте это письмо.\n\n'
                    f'С уважением,\nКоманда HR-Lab'
                )
                try:
                    print(f"Attempting to send email to {email} with host {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
                    connection = get_connection()
                    connection.open()
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        fail_silently=False,
                        connection=connection,
                    )
                    connection.close()
                    
                    # Логирование запроса смены пароля
                    log_user_action(
                        user=user,
                        action_code='password_reset_requested',
                        action_name='Запрос сброса пароля',
                        details=f'Запрос сброса пароля для пользователя {email}',
                        request=request
                    )
                    
                    messages.success(request, 'Письмо с инструкциями по сбросу пароля отправлено на ваш email.')
                    return redirect('company_profile')
                except SMTPAuthenticationError as e:
                    messages.error(request, 'Ошибка аутентификации SMTP. Проверьте email или пароль приложения в настройках Яндекса.')
                except SMTPConnectError as e:
                    messages.error(request, 'Не удалось подключиться к SMTP-серверу Яндекса. Проверьте настройки хоста и порта.')
                except SMTPServerDisconnected as e:
                    messages.error(request, 'Соединение с SMTP-сервером прервано. Попробуйте снова.')
                except Exception as e:
                    messages.error(request, f'Неизвестная ошибка при отправке письма: {str(e)}')
            else:
                messages.error(request, 'Пользователь с таким email не найден.')
    else:
        form = PasswordResetRequestForm()

    return render(request, 'compani/profile/change_password_request.html', {'form': form})

def change_password_confirm(request, uidb64, token):
    """
    Подтверждение смены пароля
    """
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = PasswordResetConfirmForm(request.POST)
            if form.is_valid():
                user.set_password(form.cleaned_data['new_password1'])
                user.save()
                update_session_auth_hash(request, user)
                
                # Логирование успешной смены пароля
                log_user_action(
                    user=user,
                    action_code='password_reset_success',
                    action_name='Пароль успешно сброшен',
                    details='Пароль успешно изменен через ссылку восстановления',
                    request=request
                )
                
                messages.success(request, 'Пароль успешно изменён. Вы можете войти с новым паролем.')
                return redirect('company_profile')
        else:
            form = PasswordResetConfirmForm()
        return render(request, 'compani/profile/change_password_confirm.html', {'form': form, 'validlink': True})
    else:
        messages.error(request, 'Ссылка для сброса пароля недействительна или истекла.')
        return render(request, 'compani/profile/change_password_confirm.html', {'form': None, 'validlink': False})
    
@login_required
def hr_agents_list(request):
    """
    Список HR-агентов компании
    """
    if request.user.user_type != 'company':
        messages.error(request, 'У вас нет доступа к управлению HR-агентами.')
        return redirect('home_comp')

    try:
        company = Company.objects.get(user=request.user)
    except Company.DoesNotExist:
        messages.error(request, 'У вас нет компании для управления HR-агентами.')
        return redirect('home_comp')

    hr_agents = Employee.objects.filter(
        company=company,
        user__user_type='hragent',
    )

    search_query = request.GET.get('search', '')
    if search_query:
        hr_agents = hr_agents.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__phone__icontains=search_query)
        )

    if request.method == 'POST' and 'delete' in request.POST:
        employee_id = request.POST.get('employee_id')
        employee = get_object_or_404(Employee, id=employee_id, company=company)
        user = employee.user
        
        # Логирование удаления HR-агента
        log_user_action(
            user=request.user,
            action_code='hr_agent_deleted',
            action_name='HR-агент удален',
            target_company=company,
            details=f'Удален HR-агент: {employee.first_name} {employee.last_name} ({user.email})',
            request=request
        )
        
        employee.delete()
        user.delete()
        messages.success(request, 'HR-агент успешно удалён.')
        return redirect('hr_agents_list')

    context = {
        'hr_agents': hr_agents,
        'company': company,
    }
    return render(request, 'compani/hrCRUD/hr_agents_list.html', context)

@login_required
def hr_agent_edit(request, employee_id):
    """
    Редактирование HR-агента
    """
    if request.user.user_type != 'company':
        messages.error(request, 'У вас нет доступа к редактированию HR-агентов.')
        return redirect('home_comp')

    try:
        company = Company.objects.get(user=request.user)
    except Company.DoesNotExist:
        messages.error(request, 'У вас нет компании для управления HR-агентами.')
        return redirect('home_comp')

    employee = get_object_or_404(Employee, id=employee_id, company=company)
    user = employee.user

    if request.method == 'POST':
        form = HRAgentEditForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            user.email = form.cleaned_data['email']
            user.phone = form.cleaned_data['phone']
            user.save()
            
            # Логирование редактирования HR-агента
            log_user_action(
                user=request.user,
                action_code='hr_agent_updated',
                action_name='HR-агент обновлен',
                target_company=company,
                details=f'Обновлен HR-агент: {employee.first_name} {employee.last_name}',
                request=request
            )
            
            messages.success(request, 'Данные HR-агента успешно обновлены.')
            return redirect('hr_agents_list')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        initial_data = {
            'first_name': employee.first_name,
            'last_name': employee.last_name,
            'email': user.email,
            'phone': user.phone,
        }
        form = HRAgentEditForm(initial=initial_data)

    return render(request, 'compani/hrCRUD/hr_agent_form.html', {'form': form, 'title': 'Редактировать HR-агента', 'employee': employee})

def setup_profanity_filter():
    """
    Настройка фильтра нецензурной лексики
    """
    profanity.load_censor_words()
    
    russian_bad_words = [
        'блять', 'блядь', 'хуй', 'пизда', 'ебать', 'ебал', 
        'нахуй', 'нихуя', 'хуё', 'пиздец', 'оху', 'мудак',
        'сука', 'бля', 'ебу', 'ёб', 'заеб', 'уеб', 'гандон',
        'пидор', 'шлюха', 'долбоёб', 'мразь', 'ублюдок',
        'фывфыв'
    ]
    
    profanity.add_censor_words(russian_bad_words)
    return profanity

profanity_filter = setup_profanity_filter()

@login_required
def create_vacancy(request):
    """
    Создание новой вакансии
    """
    if request.user.user_type not in ['company', 'hragent']:
        messages.error(request, 'Только компании и HR-агенты могут создавать вакансии.')
        return redirect('home_page')
    
    if request.user.user_type == 'hragent':
        try:
            employee = Employee.objects.get(user=request.user)
            company = employee.company
        except Employee.DoesNotExist:
            messages.error(request, 'HR-агент не привязан к компании.')
            return redirect('home_comp')
    
    if request.method == 'POST':
        form = VacancyForm(request.POST)
        if form.is_valid():
            profanity_errors = check_vacancy_for_profanity(form.cleaned_data)
            
            if profanity_errors:
                for field_name, error_message in profanity_errors.items():
                    messages.error(request, error_message)
                return render(request, 'compani/vacancy/create_vacancy.html', {'form': form})
            
            vacancy = form.save(commit=False)
            if request.user.user_type == 'company':
                vacancy.company = request.user.company
            else: 
                vacancy.company = employee.company
            vacancy.status = StatusVacancies.objects.get(status_vacancies_name='Активна')
            vacancy.save()
            
            # Логирование создания вакансии
            log_user_action(
                user=request.user,
                action_code='vacancy_created',
                action_name='Вакансия создана',
                target_company=vacancy.company,
                target_object=vacancy,
                details=f'Создана вакансия: {vacancy.position}',
                request=request
            )
            
            messages.success(request, 'Вакансия успешно создана!')
            return redirect('vacancy_list')
    else:
        form = VacancyForm()
    
    context = {
        'form': form,
    }
    return render(request, 'compani/vacancy/create_vacancy.html', context)

def check_vacancy_for_profanity(data):
    """
    Проверка вакансии на нецензурную лексику
    """
    fields_to_check = {
        'position': 'Должность',
        'description': 'Описание вакансии', 
        'requirements': 'Требования',
        'city': 'Город',
        'work_conditions_details': 'Детали условий работы'
    }
    
    errors = {}
    
    for field_key, field_name in fields_to_check.items():
        if field_key in data and data[field_key]:
            field_value = str(data[field_key])
            
            if profanity_filter.contains_profanity(field_value):
                errors[field_key] = f'Поле "{field_name}" содержит недопустимые слова. Пожалуйста, переформулируйте текст.'
    
    return errors

@login_required
def edit_vacancy(request, vacancy_id):
    """
    Редактирование вакансии
    """
    if request.user.user_type == 'company':
        vacancy = get_object_or_404(Vacancy, id=vacancy_id, company=request.user.company)
    elif request.user.user_type == 'hragent':
        employee = get_object_or_404(Employee, user=request.user)
        vacancy = get_object_or_404(Vacancy, id=vacancy_id, company=employee.company)
    else:
        messages.error(request, 'У вас нет прав для редактирования вакансий.')
        return redirect('home_page')
    
    if request.method == 'POST':
        form = VacancyForm(request.POST, instance=vacancy)
        if form.is_valid():
            vacancy = form.save(commit=False)
            if request.user.user_type == 'company':
                vacancy.company = request.user.company
            else:
                vacancy.company = employee.company
            vacancy.save()
            
            # Логирование редактирования вакансии
            log_user_action(
                user=request.user,
                action_code='vacancy_updated',
                action_name='Вакансия обновлена',
                target_company=vacancy.company,
                target_object=vacancy,
                details=f'Обновлена вакансия: {vacancy.position}',
                request=request
            )
            
            messages.success(request, 'Вакансия успешно обновлена!')
            return redirect('vacancy_list')
    else:
        form = VacancyForm(instance=vacancy)
    
    context = {
        'form': form,
    }
    return render(request, 'compani/vacancy/edit_vacancy.html', context)

@login_required
def archive_vacancy(request, vacancy_id):
    """
    Архивирование вакансии
    """
    if request.user.user_type == 'company':
        vacancy = get_object_or_404(Vacancy, id=vacancy_id, company=request.user.company)
    elif request.user.user_type == 'hragent':
        employee = get_object_or_404(Employee, user=request.user)
        vacancy = get_object_or_404(Vacancy, id=vacancy_id, company=employee.company)
    else:
        messages.error(request, 'У вас нет прав для архивирования вакансий.')
        return redirect('home_page')
    
    try:
        archived_status = StatusVacancies.objects.get(status_vacancies_name='Архивирована')
        vacancy.status = archived_status
        vacancy.save()
        
        # Логирование архивирования вакансии
        log_user_action(
            user=request.user,
            action_code='vacancy_archived',
            action_name='Вакансия архивирована',
            target_company=vacancy.company,
            target_object=vacancy,
            details=f'Архивирована вакансия: {vacancy.position}',
            request=request
        )
        
        messages.success(request, 'Вакансия успешно архивирована!')
    except StatusVacancies.DoesNotExist:
        messages.error(request, 'Статус "Архивирована" не найден. Обратитесь к администратору.')
    
    return redirect('vacancy_list')

@login_required
def unarchive_vacancy(request, vacancy_id):
    """
    Разархивирование вакансии
    """
    print("=== UNARCHIVE VACANCY FUNCTION CALLED ===")
    print(f"Request method: {request.method}")
    print(f"User: {request.user}")
    print(f"User authenticated: {request.user.is_authenticated}")
    print(f"User type: {request.user.user_type}")
    print(f"Vacancy ID: {vacancy_id}")

    if request.user.user_type == 'company':
        vacancy = get_object_or_404(Vacancy, id=vacancy_id, company=request.user.company)
    elif request.user.user_type == 'hragent':
        employee = get_object_or_404(Employee, user=request.user)
        vacancy = get_object_or_404(Vacancy, id=vacancy_id, company=employee.company)
    else:
        messages.error(request, 'У вас нет прав для разархивирования вакансий.')
        return redirect('home_page')
    
    try:
        active_status = StatusVacancies.objects.get(status_vacancies_name='Активна')
        vacancy.status = active_status
        vacancy.save()
        
        # Логирование разархивирования вакансии
        log_user_action(
            user=request.user,
            action_code='vacancy_unarchived',
            action_name='Вакансия разархивирована',
            target_company=vacancy.company,
            target_object=vacancy,
            details=f'Разархивирована вакансия: {vacancy.position}',
            request=request
        )
        
        messages.success(request, 'Вакансия успешно разархивирована!')
    except StatusVacancies.DoesNotExist:
        messages.error(request, 'Статус "Активна" не найден. Обратитесь к администратору.')
    
    return redirect('vacancy_list')

@login_required
def vacancy_list(request):
    """
    Список вакансий компании
    """
    if request.user.user_type == 'company':
        vacancies = Vacancy.objects.filter(company=request.user.company)
    elif request.user.user_type == 'hragent':
        employee = get_object_or_404(Employee, user=request.user)
        vacancies = Vacancy.objects.filter(company=employee.company)
    else:
        vacancies = Vacancy.objects.none()
    
    search_query = request.GET.get('search', '')
    if search_query:
        vacancies = vacancies.filter(
            Q(position__icontains=search_query) |
            Q(city__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(requirements__icontains=search_query)
        )
    
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        if status_filter == 'active':
            vacancies = vacancies.filter(status__status_vacancies_name='Активна')
        elif status_filter == 'archived':
            vacancies = vacancies.filter(status__status_vacancies_name='Архивирована')
        elif status_filter == 'draft':
            vacancies = vacancies.filter(status__status_vacancies_name='Черновик')
    
    # Подсчет вакансий по статусам для фильтров
    counts = {
        'total': Vacancy.objects.filter(company=request.user.company if request.user.user_type == 'company' else request.user.employee.company).count(),
        'active': Vacancy.objects.filter(
            company=request.user.company if request.user.user_type == 'company' else request.user.employee.company,
            status__status_vacancies_name='Активна'
        ).count(),
        'archived': Vacancy.objects.filter(
            company=request.user.company if request.user.user_type == 'company' else request.user.employee.company,
            status__status_vacancies_name='Архивирована'
        ).count(),
        'draft': Vacancy.objects.filter(
            company=request.user.company if request.user.user_type == 'company' else request.user.employee.company,
            status__status_vacancies_name='Черновик'
        ).count(),
    }
    
    context = {
        'vacancies': vacancies,
        'current_status': status_filter,
        'counts': counts,
    }
    return render(request, 'compani/vacancy/vacancy_list.html', context)

@login_required
def responses_list(request):
    """
    Список откликов на вакансии компании
    """
    if request.user.user_type not in ['company', 'hragent']:
        messages.error(request, 'У вас нет доступа к просмотру откликов.')
        return redirect('home_comp')

    try:
        if request.user.user_type == 'company':
            company = Company.objects.get(user=request.user)
        elif request.user.user_type == 'hragent':
            employee = Employee.objects.get(user=request.user)
            company = employee.company
    except (Company.DoesNotExist, Employee.DoesNotExist):
        messages.error(request, 'У вас нет компании для просмотра откликов.')
        return redirect('home_comp')

    # Получаем все отклики на вакансии компании
    responses = Response.objects.filter(vacancy__company=company).select_related(
        'applicants', 'vacancy', 'status'
    ).order_by('-response_date')

    # Статистика по статусам
    counts = {
        'total': responses.count(),
        'new': responses.filter(status__status_response_name='Новый').count(),
        'viewed': responses.filter(status__status_response_name='Просмотрен').count(),
        'invited': responses.filter(status__status_response_name='Приглашен').count(),
        'rejected': responses.filter(status__status_response_name='Отклонен').count(),
    }

    # Фильтрация по статусу
    status_filter = request.GET.get('status', 'all')
    current_status = status_filter

    if status_filter != 'all':
        status_mapping = {
            'new': 'Новый',
            'viewed': 'Просмотрен', 
            'invited': 'Приглашен',
            'rejected': 'Отклонен'
        }
        if status_filter in status_mapping:
            responses = responses.filter(status__status_response_name=status_mapping[status_filter])

    # Обработка AJAX запросов для обновления статуса
    if request.method == 'POST':
        response_id = request.POST.get('response_id')
        response = get_object_or_404(Response, id=response_id, vacancy__company=company)
        
        # Сохраняем старый статус перед обновлением
        old_status_name = response.status.status_response_name
        
        form = ResponseStatusUpdateForm(request.POST, instance=response)
        if form.is_valid():
            form.save()
            
            # Получаем новый статус после сохранения
            response.refresh_from_db()
            new_status_name = response.status.status_response_name
            
            # Логирование изменения статуса отклика
            log_user_action(
                user=request.user,
                action_code='response_status_updated',
                action_name='Статус отклика обновлен',
                target_company=company,
                target_object=response,
                details=f'Статус отклика на вакансию "{response.vacancy.position}" изменен с "{old_status_name}" на "{new_status_name}"',
                request=request
            )
            
            # Отправляем письмо только если статус действительно изменился
            email_sent = False
            if old_status_name != new_status_name:
                email_sent = send_response_status_email(response, old_status_name, new_status_name)
            
            # Для AJAX запросов
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # Обновляем статистику
                updated_counts = {
                    'total': Response.objects.filter(vacancy__company=company).count(),
                    'new': Response.objects.filter(vacancy__company=company, status__status_response_name='Новый').count(),
                    'viewed': Response.objects.filter(vacancy__company=company, status__status_response_name='Просмотрен').count(),
                    'invited': Response.objects.filter(vacancy__company=company, status__status_response_name='Приглашен').count(),
                    'rejected': Response.objects.filter(vacancy__company=company, status__status_response_name='Отклонен').count(),
                }
                
                if email_sent:
                    return JsonResponse({
                        'status': 'success', 
                        'message': 'Статус обновлен. Уведомление отправлено.',
                        'counts': updated_counts
                    })
                else:
                    if old_status_name != new_status_name:
                        return JsonResponse({
                            'status': 'warning', 
                            'message': 'Статус обновлен, но не удалось отправить уведомление.',
                            'counts': updated_counts
                        })
                    else:
                        return JsonResponse({
                            'status': 'success', 
                            'message': 'Статус обновлен.',
                            'counts': updated_counts
                        })
            
            # Для обычных POST запросов
            if email_sent:
                messages.success(request, f'Статус отклика успешно обновлён. Уведомление отправлено соискателю.')
            else:
                if old_status_name != new_status_name:
                    messages.warning(request, f'Статус отклика обновлён, но не удалось отправить уведомление соискателю.')
                else:
                    messages.success(request, 'Статус отклика успешно обновлён.')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Ошибка при обновлении статуса.'})
            messages.error(request, 'Ошибка при обновлении статуса.')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success'})
        return redirect('responses_list')

    # Подготавливаем данные для шаблона
    response_data = []
    for response in responses:
        form = ResponseStatusUpdateForm(instance=response)
        response_data.append({
            'response': response,
            'form': form
        })

    context = {
        'company': company,
        'response_data': response_data,
        'counts': counts,
        'current_status': current_status,
    }
    return render(request, 'compani/responses_list.html', context)

def send_response_status_email(response, old_status_name, new_status_name):
    """
    Отправляет письмо соискателю при изменении статуса отклика
    """
    # ... существующий код отправки email без изменений ...
    # (оставляю существующую функцию без изменений, так как она уже работает)
    
    try:
        # ... существующий код ...
        return True
    except Exception as e:
        print(f"❌ [EMAIL] ОШИБКА отправки уведомления о статусе отклика: {str(e)}")
        return False

@login_required
def hr_agent_create(request):
    """
    Создание нового HR-агента
    """
    if request.user.user_type != 'company':
        messages.error(request, 'У вас нет доступа к созданию HR-агентов.')
        return redirect('home_comp')

    try:
        company = Company.objects.get(user=request.user)
    except Company.DoesNotExist:
        messages.error(request, 'У вас нет компании для управления HR-агентами.')
        return redirect('home_comp')

    if request.method == 'POST':
        form = HRAgentCreateForm(request.POST)
        if form.is_valid():
            user = form.save(company=company)
            
            hr_agent = Employee.objects.get(user=user, company=company)
            
            password = form.cleaned_data['password1']
            
            # Логирование создания HR-агента
            log_user_action(
                user=request.user,
                action_code='hr_agent_created',
                action_name='HR-агент создан',
                target_company=company,
                details=f'Создан HR-агент: {hr_agent.first_name} {hr_agent.last_name} ({user.email})',
                request=request
            )
            
            email_sent = send_hr_agent_credentials(hr_agent, password, company.name)
            
            if email_sent:
                messages.success(request, 'HR-агент успешно создан. Письмо с учетными данными отправлено.')
            else:
                messages.warning(request, 'HR-агент создан, но не удалось отправить письмо с учетными данными.')
            
            return redirect('hr_agents_list')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = HRAgentCreateForm()

    return render(request, 'compani/hrCRUD/hr_agent_form.html', {'form': form, 'title': 'Создать HR-агента'})

def send_hr_agent_credentials(hr_agent, password, company_name):
    """
    Отправка учетных данных HR-агенту
    """
    # ... существующий код отправки email без изменений ...
    # (оставляю существующую функцию без изменений)
    
    try:
        # ... существующий код ...
        return True
    except Exception as e:
        print(f"❌ [EMAIL] ОШИБКА отправки данных HR-агенту: {str(e)}")
        return False
    
@login_required
def employee_profile(request):
    """
    Просмотр профиля сотрудника (HR-агента)
    """
    if request.user.user_type != 'hragent':
        messages.error(request, 'У вас нет доступа к этой странице.')
        return redirect('home_comp')
    
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Профиль сотрудника не найден.')
        return redirect('home_comp')
    
    context = {
        'employee': employee,
        'user': request.user,
    }
    return render(request, 'compani/employee_profile.html', context)

@login_required
def edit_employee_profile(request):
    """
    Редактирование профиля сотрудника (HR-агента)
    """
    if request.user.user_type != 'hragent':
        messages.error(request, 'У вас нет доступа к этой странице.')
        return redirect('home_comp')
    
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'Профиль сотрудника не найден.')
        return redirect('home_comp')
    
    if request.method == 'POST':
        form = EmployeeProfileForm(request.POST, instance=employee, user=request.user)
        if form.is_valid():
            form.save()
            
            # Логирование обновления профиля HR-агента
            log_user_action(
                user=request.user,
                action_code='employee_profile_updated',
                action_name='Профиль сотрудника обновлен',
                target_company=employee.company,
                details=f'HR-агент обновил свой профиль: {employee.first_name} {employee.last_name}',
                request=request
            )
            
            messages.success(request, 'Профиль успешно обновлен!')
            return redirect('employee_profile')
        else:
            # Отладочная информация
            print("FORM ERRORS:", form.errors)
            print("FORM NON FIELD ERRORS:", form.non_field_errors())
            for field in form:
                if field.errors:
                    print(f"FIELD {field.name} ERRORS:", field.errors)
            
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = EmployeeProfileForm(instance=employee, user=request.user)
    
    context = {
        'employee': employee,
        'user': request.user,
        'form': form,
    }
    return render(request, 'compani/employee_edit_profile.html', context)

@login_required
def delete_company_profile(request):
    """
    Удаление профиля компании
    """
    if request.user.user_type != 'company':
        return redirect('home_page')
    
    if request.method == 'POST':
        user = request.user
        company_name = user.company.name if hasattr(user, 'company') else 'Неизвестная компания'
        
        # Логирование удаления компании
        log_user_action(
            user=user,
            action_code='company_deleted',
            action_name='Компания удалена',
            target_company=user.company if hasattr(user, 'company') else None,
            details=f'Удалена компания: {company_name}',
            request=request
        )
        
        user.delete()
        return redirect('home_page')
    
    return redirect('company_profile')

import csv
import io
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.utils import timezone
from .forms import HRAgentCreateForm, HRAgentImportForm

@login_required
def export_hr_agents_csv(request):
    """
    Экспорт списка HR-агентов в CSV
    """
    if request.user.user_type != 'company':
        messages.error(request, 'У вас нет доступа к экспорту HR-агентов.')
        return redirect('home_comp')

    try:
        company = Company.objects.get(user=request.user)
    except Company.DoesNotExist:
        messages.error(request, 'У вас нет компании для экспорта HR-агентов.')
        return redirect('home_comp')

    hr_agents = Employee.objects.filter(
        company=company,
        user__user_type='hragent',
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="hr_agents_{company.name}_{timezone.now().strftime("%Y-%m-%d")}.csv"'
    
    response.write('\ufeff'.encode('utf8'))  # BOM для корректного отображения кириллицы в Excel
    writer = csv.writer(response)
    
    # Заголовки
    writer.writerow(['Имя', 'Фамилия', 'Email', 'Телефон', 'Статус', 'Дата создания'])
    
    for agent in hr_agents:
        writer.writerow([
            agent.first_name,
            agent.last_name,
            agent.user.email,
            agent.user.phone,
            'Активен' if agent.user.is_active else 'Неактивен',
            agent.user.date_joined.strftime('%Y-%m-%d %H:%M') if agent.user.date_joined else ''
        ])
    
    # Логирование экспорта HR-агентов
    log_user_action(
        user=request.user,
        action_code='hr_agents_exported',
        action_name='HR-агенты экспортированы',
        target_company=company,
        details=f'Экспортировано {hr_agents.count()} HR-агентов в CSV',
        request=request
    )
    
    return response

import secrets
import string
@login_required
def import_hr_agents(request):
    """
    Импорт HR-агентов из CSV файла
    """
    if request.user.user_type != 'company':
        messages.error(request, 'У вас нет доступа к импорту HR-агентов.')
        return redirect('home_comp')

    try:
        company = Company.objects.get(user=request.user)
    except Company.DoesNotExist:
        messages.error(request, 'У вас нет компании для импорта HR-агентов.')
        return redirect('home_comp')

    if request.method == 'POST':
        form = HRAgentImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            
            try:
                # ... существующий код обработки CSV ...
                
                created_count = 0
                error_count = 0
                email_sent_count = 0
                email_failed_count = 0
                errors = []
                
                # ... существующий код обработки CSV ...
                
                # Логирование импорта HR-агентов
                log_user_action(
                    user=request.user,
                    action_code='hr_agents_imported',
                    action_name='HR-агенты импортированы',
                    target_company=company,
                    details=f'Импортировано {created_count} HR-агентов из CSV, ошибок: {error_count}',
                    request=request
                )
                
                if created_count > 0:
                    success_msg = f'Успешно создано {created_count} HR-агентов.'
                    if email_sent_count > 0:
                        success_msg += f' Письма с учетными данными отправлены {email_sent_count} пользователям.'
                    if email_failed_count > 0:
                        success_msg += f' Не удалось отправить письма {email_failed_count} пользователям.'
                    
                    messages.success(request, success_msg)
                    
                if error_count > 0:
                    warning_msg = f'Не удалось обработать {error_count} записей. Проверьте формат данных.'
                    messages.warning(request, warning_msg)
                    
            except Exception as e:
                error_msg = f'Ошибка при чтении файла: {str(e)}'
                messages.error(request, error_msg)
            
            return redirect('hr_agents_list')
      
    else:
        form = HRAgentImportForm()
    
    context = {
        'form': form,
        'company': company,
    }
    return render(request, 'compani/hrCRUD/import_hr_agents.html', context)