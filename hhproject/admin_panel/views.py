from pathlib import Path
import subprocess
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.core.files import File
from datetime import timedelta
import os

from django.urls import reverse
from matplotlib import pyplot as plt

from .procedure_manager import DjangoBackupManager
from .forms import AdminProfileEditForm, BackupUploadForm, SiteAdminCreateForm, SiteAdminEditForm

from home.models import Company, Complaint, User, Employee, Vacancy, StatusVacancies
from home.models import Backup, AdminLog
from .forms import CompanyModerationForm

def is_admin(user):
    """Проверка что пользователь администратор (суперпользователь или adminsite)"""
    return user.is_authenticated and (user.is_superuser or user.user_type == 'adminsite')

def is_superuser_only(user):
    """Проверка что пользователь ТОЛЬКО суперпользователь"""
    return user.is_authenticated and user.is_superuser

def get_admin_context(request):
    pending_count = Company.objects.filter(status=Company.STATUS_PENDING).count()
    site_admins_count = User.objects.filter(user_type='adminsite', is_active=True).count()
    
    return {
        'pending_companies_count': pending_count,
        'site_admins_count': site_admins_count,
        'is_superuser': request.user.is_superuser,
    }

@user_passes_test(is_admin, login_url='/admin/login/')
def admin_dashboard(request):
    """Главная страница админки"""
    context = get_admin_context(request)
    
    pending_companies = Company.objects.filter(status=Company.STATUS_PENDING)
    total_companies = Company.objects.count()
    approved_companies = Company.objects.filter(status=Company.STATUS_APPROVED).count()
    rejected_companies = Company.objects.filter(status=Company.STATUS_REJECTED).count()
    pending_complaints_count = Complaint.objects.filter(status='pending').count()
    
    # Последние логи
    recent_logs = AdminLog.objects.all().order_by('-created_at')[:10]
    
    # Статистика пользователей
    total_users = User.objects.count()
    company_users = User.objects.filter(user_type='company').count()
    applicant_users = User.objects.filter(user_type='applicant').count()
    
    context.update({
        'pending_count': pending_companies.count(),
        'total_companies': total_companies,
        'approved_companies': approved_companies,
        'rejected_companies': rejected_companies,
        'total_users': total_users,
        'company_users': company_users,
        'applicant_users': applicant_users,
        'recent_logs': recent_logs,
        'pending_complaints_count': pending_complaints_count,
    })
    return render(request, 'admin_panel/dashboard.html', context)

from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

@user_passes_test(is_admin, login_url='/admin/login/')
def company_moderation(request):
    """Страница модерации компаний"""
    context = get_admin_context(request)
    
    companies = Company.objects.all().order_by('-created_at')
    pending_companies = companies.filter(status=Company.STATUS_PENDING)
    
    if request.method == 'POST':
        company_id = request.POST.get('company_id')
        status = request.POST.get('status')
        
        if company_id and status:
            try:
                company = Company.objects.get(id=company_id)
                
                old_status = company.status
                company.status = status
                company.save()
                
                if old_status != company.status:
                    # Отправка email уведомления
                    email_sent = send_company_status_email(company, old_status)
                    
                    if company.status == Company.STATUS_APPROVED:
                        action = 'company_approved'
                        details = f'Компания {company.name} одобрена'
                    elif company.status == Company.STATUS_REJECTED:
                        action = 'company_rejected'
                        details = f'Компания {company.name} отклонена'
                    else:
                        action = 'company_updated'
                        details = f'Статус компании {company.name} изменен на {company.get_status_display()}'
                    
                    # Добавляем информацию об email в детали
                    if email_sent:
                        details += ' (email отправлен)'
                    else:
                        details += ' (ошибка отправки email)'
                    
                    AdminLog.objects.create(
                        admin=request.user,
                        action=action,
                        target_company=company,
                        details=details
                    )
            except:
                pass
                    
    context.update({
        'pending_companies': pending_companies,
        'all_companies': companies,
        'status_choices': Company.STATUS_CHOICES,
    })
    return render(request, 'admin_panel/company_moderation.html', context)

@user_passes_test(is_admin, login_url='/admin/login/')
def company_detail(request, company_id):
    context = get_admin_context(request)
    
    company = get_object_or_404(Company, id=company_id)
    
    if request.method == 'POST':
        form = CompanyModerationForm(request.POST, instance=company)
        if form.is_valid():
            old_status = company.status
            company = form.save()
            
            if old_status != company.status:
                send_company_status_email(company, old_status)
                
                if company.status == Company.STATUS_APPROVED:
                    action = 'company_approved'
                    details = f'Компания {company.name} одобрена через детальную страницу'
                elif company.status == Company.STATUS_REJECTED:
                    action = 'company_rejected' 
                    details = f'Компания {company.name} отклонена через детальную страницу'
                else:
                    action = 'company_updated'
                    details = f'Статус компании {company.name} изменен на {company.get_status_display()}'
                
                AdminLog.objects.create(
                    admin=request.user,
                    action=action,
                    target_company=company,
                    details=details
                )
            
            return redirect('admin_company_moderation')
    else:
        form = CompanyModerationForm(instance=company)
    
    context.update({
        'company': company,
        'form': form,
    })
    return render(request, 'admin_panel/company_detail.html', context)

def send_company_status_email(company, old_status):
    
    user_email = company.user.email
    company_name = company.name
    new_status = company.status
    status_display = company.get_status_display()
    
    if new_status == 'approved':
        status_title = "Компания одобрена!"
        status_description = "Ваша компания успешно прошла модерацию и теперь может размещать вакансии на нашей платформе."
        status_icon = "🎉"
        status_color = "#10b981"
    elif new_status == 'rejected':
        status_title = "Требуется внимание"
        status_description = "К сожалению, ваша компания не прошла модерацию. Пожалуйста, свяжитесь с поддержкой для уточнения деталей."
        status_icon = "⚠️"
        status_color = "#ef4444"
    else:
        status_title = "Статус обновлен"
        status_description = f"Статус вашей компании изменен на: {status_display}"
        status_icon = "📋"
        status_color = "#2563eb"
    
    try:
        subject = f'Статус вашей компании на HR-Lab изменен'
        
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
                .header p {{
                    margin: 10px 0 0 0;
                    opacity: 0.9;
                    font-size: 16px;
                }}
                .content {{
                    padding: 40px 30px;
                }}
                .status-card {{
                    background: rgba(37, 99, 235, 0.05);
                    border: 1px solid rgba(37, 99, 235, 0.2);
                    border-radius: 15px;
                    padding: 25px;
                    margin: 25px 0;
                    text-align: center;
                }}
                .status-icon {{
                    font-size: 48px;
                    margin-bottom: 15px;
                }}
                .status-title {{
                    font-size: 20px;
                    font-weight: 700;
                    color: #1e293b;
                    margin-bottom: 10px;
                }}
                .status-description {{
                    color: #64748b;
                    font-size: 16px;
                    line-height: 1.5;
                }}
                .approved {{
                    background: rgba(16, 185, 129, 0.05);
                    border-color: rgba(16, 185, 129, 0.2);
                }}
                .approved .status-title {{
                    color: #065f46;
                }}
                .rejected {{
                    background: rgba(239, 68, 68, 0.05);
                    border-color: rgba(239, 68, 68, 0.2);
                }}
                .rejected .status-title {{
                    color: #991b1b;
                }}
                .action-button {{
                    display: inline-block;
                    background: linear-gradient(45deg, #2563eb, #1e40af);
                    color: white;
                    padding: 14px 32px;
                    text-decoration: none;
                    border-radius: 25px;
                    font-weight: 600;
                    font-size: 16px;
                    margin: 20px 0;
                    transition: all 0.3s ease;
                }}
                .action-button:hover {{
                    background: linear-gradient(45deg, #1e40af, #2563eb);
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(37, 99, 235, 0.3);
                }}
                .info-section {{
                    background: #f8fafc;
                    border-radius: 12px;
                    padding: 20px;
                    margin: 25px 0;
                }}
                .info-item {{
                    display: flex;
                    justify-content: space-between;
                    padding: 10px 0;
                    border-bottom: 1px solid #e2e8f0;
                }}
                .info-item:last-child {{
                    border-bottom: none;
                }}
                .info-label {{
                    color: #64748b;
                    font-weight: 500;
                }}
                .info-value {{
                    color: #1e293b;
                    font-weight: 600;
                }}
                .footer {{
                    background: #f1f5f9;
                    padding: 30px;
                    text-align: center;
                    border-top: 1px solid #e2e8f0;
                }}
                .footer p {{
                    margin: 5px 0;
                    color: #64748b;
                    font-size: 14px;
                }}
                .contact-info {{
                    margin-top: 15px;
                    padding-top: 15px;
                    border-top: 1px solid #e2e8f0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>HR-Lab</h1>
                    <p>Уведомление о статусе компании</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #1e293b; margin-top: 0;">Уважаемый представитель компании!</h2>
                    <p style="color: #64748b; font-size: 16px;">
                        Статус вашей компании <strong>"{company_name}"</strong> на платформе HR-Lab был обновлен.
                    </p>
                    
                    <div class="status-card {new_status}">
                        <div class="status-icon">{status_icon}</div>
                        <div class="status-title">{status_title}</div>
                        <div class="status-description">{status_description}</div>
                    </div>
                    
                    <div class="info-section">
                        <div class="info-item">
                            <span class="info-label">Компания:</span>
                            <span class="info-value">{company_name}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">Новый статус:</span>
                            <span class="info-value" style="color: {status_color}; font-weight: 700;">
                                {status_display}
                            </span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">Дата обновления:</span>
                            <span class="info-value">{company.created_at.strftime('%d.%m.%Y')}</span>
                        </div>
                    </div>
                    
                    <p style="color: #64748b; font-size: 15px; text-align: center;">
                        Если у вас возникли вопросы, не стесняйтесь обращаться в нашу службу поддержки.
                    </p>
                </div>
                
                <div class="footer">
                    <p><strong>С уважением, команда HR-Lab</strong></p>
                    <p>Мы помогаем компаниям находить лучших сотрудников</p>
                    <div class="contact-info">
                        <p>Email: hr-labogency@mail.ru</p>
                    </div>
                    <p style="font-size: 12px; margin-top: 20px; color: #94a3b8;">
                        Это автоматическое сообщение, пожалуйста, не отвечайте на него.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Текстовая версия для почтовых клиентов, которые не поддерживают HTML
        plain_message = f"""
        Уважаемый представитель компании "{company_name}"!

        Статус вашей компании на платформе HR-Lab был изменен.

        Новый статус: {status_display}

        {status_description}

        Для управления вашей компанией перейдите в личный кабинет:
        http://127.0.0.1:8000/compani/

        С уважением,
        Команда HR-Lab

        ---
        Email: support@hr-lab.ru
        Телефон: +7 (999) 123-45-67
        """
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=False,
        )
        
        return True
        
    except Exception as e:
        print(f"[EMAIL] ОШИБКА: {str(e)}")
        return False

@user_passes_test(is_admin, login_url='/admin/login/')
def vacancy_management(request):
    context = get_admin_context(request)
    
    vacancies = Vacancy.objects.all().select_related('company', 'status').order_by('-created_date')
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        vacancies = vacancies.filter(status__id=status_filter)
    
    search_query = request.GET.get('search', '')
    if search_query:
        vacancies = vacancies.filter(position__icontains=search_query)
    
    context.update({
        'vacancies': vacancies,
        'status_choices': StatusVacancies.objects.all(),
        'current_status': status_filter,
        'search_query': search_query,
    })
    return render(request, 'admin_panel/vacancy_management.html', context)
# views.py
# views.py
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import user_passes_test
from django.core.files import File
import os


@user_passes_test(is_admin, login_url='/admin/login/')
def backup_dashboard(request):
    """Главная панель управления бэкапами"""
    context = get_admin_context(request)
    backup_manager = DjangoBackupManager()
    
    # Получаем информацию о системе
    system_info = backup_manager.get_system_info()
    
    # Получаем список бэкапов из БД
    backups = Backup.objects.all().order_by('-created_at')
    
    # Тестируем подключение к БД
    connection_test = backup_manager.test_connection()
    
    context.update({
        'system_info': system_info,
        'backups': backups,
        'connection_test': connection_test,
        'upload_form': BackupUploadForm(),
        'backup_types': Backup.BACKUP_TYPES,
    })
    
    return render(request, 'admin_panel/backup_management.html', context)

# Глобальная переменная для хранения прогресса (в продакшене используйте Redis или БД)
current_progress = {"message": "", "percent": 0}

@user_passes_test(is_admin, login_url='/admin/login/')
def create_backup_api(request):
    """API для создания бэкапа с отслеживанием прогресса"""
    if request.method == 'POST':
        backup_type = request.POST.get('type', 'database')
        custom_name = request.POST.get('custom_name', '')
        
        backup_manager = DjangoBackupManager()
        
        # Сбрасываем прогресс
        global current_progress
        current_progress = {"message": "Начинаем создание бэкапа...", "percent": 0}
        
        def progress_callback(message, percent=None):
            global current_progress
            current_progress = {
                "message": message,
                "percent": percent if percent is not None else current_progress["percent"]
            }
            print(f"Backup Progress: {percent}% - {message}")  # Логируем в консоль
        
        backup_manager.set_progress_callback(progress_callback)
        
        try:
            result = backup_manager.create_backup(
                backup_type=backup_type, 
                custom_name=custom_name,
                user=request.user
            )
            
            if result['success']:
                # Сохраняем в базу данных
                backup = Backup(
                    name=result['filename'],
                    backup_type=backup_type,
                    file_size=result['file_size'],
                    created_by=request.user
                )
                
                # Сохраняем файл
                with open(result['filepath'], 'rb') as f:
                    backup.backup_file.save(result['filename'], File(f))
                backup.save()
                
                # Удаляем временный файл
                if os.path.exists(result['filepath']):
                    os.remove(result['filepath'])
                
                # Логируем
                AdminLog.objects.create(
                    admin=request.user,
                    action='backup_created',
                    details=f"Создан бэкап: {result['filename']}"
                )
                
                return JsonResponse({
                    'success': True, 
                    'message': 'Бэкап успешно создан',
                    'filename': result['filename']
                })
            else:
                return JsonResponse({
                    'success': False, 
                    'error': result.get('error', 'Ошибка при создании бэкапа')
                }, status=400)
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Backup creation error: {error_details}")
            
            return JsonResponse({
                'success': False, 
                'error': f'Ошибка при создании бэкапа: {str(e)}'
            }, status=400)
    
    return JsonResponse({'error': 'Invalid method'}, status=405)
from django.views.decorators.csrf import csrf_exempt
@csrf_exempt
def backup_progress_api(request):
    """API для получения текущего прогресса бэкапа"""
    global current_progress
    return JsonResponse(current_progress)

@user_passes_test(is_admin, login_url='/admin/login/')
def upload_backup_api(request):
    """API для загрузки бэкапа"""
    if request.method == 'POST':
        form = BackupUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            backup_file = request.FILES['backup_file']
            backup_manager = DjangoBackupManager()
            
            try:
                # Проверяем бэкап
                if not backup_manager.validate_backup(backup_file):
                    return JsonResponse({
                        'success': False,
                        'error': 'Файл бэкапа поврежден или имеет неверный формат'
                    }, status=400)
                
                # Определяем тип бэкапа по расширению
                backup_type = 'database'
                if backup_file.name.endswith('.zip'):
                    backup_type = 'full'
                
                # Сохраняем бэкап
                backup = Backup(
                    name=backup_file.name,
                    backup_type=backup_type,
                    file_size=backup_file.size,
                    created_by=request.user
                )
                backup.backup_file.save(backup_file.name, backup_file)
                backup.save()
                
                AdminLog.objects.create(
                    admin=request.user,
                    action='backup_uploaded',
                    details=f"Загружен бэкап: {backup_file.name}"
                )
                
                return JsonResponse({
                    'success': True,
                    'message': 'Бэкап успешно загружен'
                })
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'error': f'Ошибка загрузки бэкапа: {str(e)}'
                }, status=400)
        else:
            return JsonResponse({
                'success': False,
                'error': 'Ошибка валидации формы'
            }, status=400)
    
    return JsonResponse({'error': 'Invalid method'}, status=405)

def get_media_stats(self):
    """Получение статистики медиа файлов"""
    media_dir = Path(settings.MEDIA_ROOT)
    stats = {
        'exists': False,
        'total_files': 0,
        'total_size': 0,
        'file_types': {},
        'largest_files': []
    }
    
    if media_dir.exists():
        stats['exists'] = True
        media_files = []
        
        try:
            # Собираем информацию о файлах
            for file_path in media_dir.rglob('*'):
                if file_path.is_file():
                    try:
                        file_size = file_path.stat().st_size
                        file_ext = file_path.suffix.lower()
                        
                        stats['total_files'] += 1
                        stats['total_size'] += file_size
                        
                        # Считаем типы файлов
                        stats['file_types'][file_ext] = stats['file_types'].get(file_ext, 0) + 1
                        
                        # Сохраняем информацию о файле для крупнейших
                        media_files.append((file_path, file_size))
                        
                    except Exception as e:
                        print(f"Error processing file {file_path}: {e}")
                        continue
            
            # Сортируем по размеру и берем 10 крупнейших
            media_files.sort(key=lambda x: x[1], reverse=True)
            stats['largest_files'] = [(str(path), size) for path, size in media_files[:10]]
            
        except Exception as e:
            print(f"Error scanning media directory: {e}")
    
    return stats

@user_passes_test(is_admin, login_url='/admin/login/')
def media_stats_api(request):
    """API для получения статистики медиа файлов"""
    backup_manager = DjangoBackupManager()
    stats = backup_manager.get_media_stats()
    
    # Форматируем размеры для отображения
    stats['total_size_formatted'] = backup_manager._format_file_size(stats['total_size'])
    stats['largest_files_formatted'] = [
        (path, backup_manager._format_file_size(size)) 
        for path, size in stats['largest_files']
    ]
    
    return JsonResponse(stats)

@user_passes_test(is_admin, login_url='/admin/login/')
def restore_backup_api(request, backup_id):
    """API для восстановления из бэкапа"""
    if request.method == 'POST':
        backup = get_object_or_404(Backup, id=backup_id)
        backup_manager = DjangoBackupManager()
        
        try:
            # Дополнительное подтверждение для критических операций
            if not request.POST.get('confirmed'):
                return JsonResponse({
                    'requires_confirmation': True,
                    'message': 'ВНИМАНИЕ: Восстановление базы данных перезапишет все текущие данные. Это действие нельзя отменить. Подтвердите восстановление.'
                })
            
            # Проверяем существование файла
            if not backup.backup_file:
                return JsonResponse({
                    'success': False,
                    'error': 'Файл бэкапа не найден'
                }, status=404)
            
            # Открываем файл для чтения
            with backup.backup_file.open('rb') as f:
                # Восстанавливаем бэкап
                result = backup_manager.restore_backup(f, request.user)
            
            if result['success']:
                AdminLog.objects.create(
                    admin=request.user,
                    action='backup_restored',
                    details=f"Восстановлен бэкап: {backup.name}"
                )
                
                return JsonResponse({
                    'success': True, 
                    'message': result['message'] or 'База данных успешно восстановлена'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': result.get('error', 'Ошибка при восстановлении')
                }, status=400)
                
        except Exception as e:
            error_message = str(e)
            print(f"Restore error: {error_message}")
            return JsonResponse({
                'success': False, 
                'error': f'Ошибка восстановления: {error_message}'
            }, status=500)
    
    return JsonResponse({'error': 'Invalid method'}, status=405)

@user_passes_test(is_admin, login_url='/admin/login/')
def download_backup_api(request, backup_id):
    """Скачивание бэкапа"""
    backup = get_object_or_404(Backup, id=backup_id)
    
    try:
        if not backup.backup_file:
            return JsonResponse({
                'success': False,
                'error': 'Файл бэкапа не найден'
            }, status=404)
        
        response = HttpResponse(backup.backup_file, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{backup.name}"'
        response['Content-Length'] = backup.backup_file.size
        
        AdminLog.objects.create(
            admin=request.user,
            action='backup_downloaded',
            details=f"Скачан бэкап: {backup.name}"
        )
        
        return response
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Ошибка скачивания: {str(e)}'
        }, status=400)

@user_passes_test(is_admin, login_url='/admin/login/')
def delete_backup_api(request, backup_id):
    """Удаление бэкапа"""
    if request.method == 'POST':
        backup = get_object_or_404(Backup, id=backup_id)
        
        try:
            backup_name = backup.name
            backup.delete()
            
            AdminLog.objects.create(
                admin=request.user,
                action='backup_deleted',
                details=f"Удален бэкап: {backup_name}"
            )
            
            return JsonResponse({
                'success': True, 
                'message': 'Бэкап успешно удален'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'error': str(e)
            }, status=400)
    
    return JsonResponse({'error': 'Invalid method'}, status=405)

@user_passes_test(is_admin, login_url='/admin/login/')
def get_backups_list_api(request):
    """API для получения списка бэкапов"""
    try:
        backups = Backup.objects.all().order_by('-created_at')
        backups_data = []
        
        for backup in backups:
            backups_data.append({
                'id': backup.id,
                'name': backup.name,
                'backup_type': backup.backup_type,
                'backup_type_display': backup.get_backup_type_display(),
                'file_size': backup.file_size,
                'file_size_display': backup.get_file_size_display(),
                'created_at': backup.created_at.strftime('%d.%m.%Y %H:%M'),
                'created_by': backup.created_by.username,
                'download_url': reverse('admin_download_backup', args=[backup.id]),
            })
        
        return JsonResponse({
            'success': True,
            'backups': backups_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@user_passes_test(is_admin, login_url='/admin/login/')
def system_status_api(request):
    """API для получения статуса системы"""
    backup_manager = DjangoBackupManager()
    system_info = backup_manager.get_system_info()
    
    return JsonResponse(system_info)

@user_passes_test(is_admin, login_url='/admin/login/')
def admin_logs(request):
    """Просмотр логов администраторов"""
    context = get_admin_context(request)
    
    logs = AdminLog.objects.all().order_by('-created_at')
    
    action_filter = request.GET.get('action', '')
    if action_filter:
        logs = logs.filter(action=action_filter)
    
    search_query = request.GET.get('search', '')
    if search_query:
        logs = logs.filter(details__icontains=search_query)
    
    context.update({
        'logs': logs,
        'action_choices': AdminLog.ACTION_CHOICES,
        'current_action': action_filter,
        'search_query': search_query,
    })
    return render(request, 'admin_panel/admin_logs.html', context)

@user_passes_test(is_admin, login_url='/admin/login/')
def clear_logs(request):
    """Очистка логов"""
    if request.method == 'POST':
        from datetime import datetime
        days_old = int(request.POST.get('days_old', 30))
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        deleted_count = AdminLog.objects.filter(created_at__lt=cutoff_date).delete()[0]
        
        AdminLog.objects.create(
            admin=request.user,
            action='logs_cleared',
            details=f'Очищено {deleted_count} логов старше {days_old} дней'
        )
        
    
    return redirect('admin_logs')

@user_passes_test(is_admin, login_url='/admin/login/')
def api_company_stats(request):
    """API для получения статистики компаний"""
    stats = {
        'pending': Company.objects.filter(status=Company.STATUS_PENDING).count(),
        'approved': Company.objects.filter(status=Company.STATUS_APPROVED).count(),
        'rejected': Company.objects.filter(status=Company.STATUS_REJECTED).count(),
        'total': Company.objects.count(),
    }
    return JsonResponse(stats)

@user_passes_test(is_admin, login_url='/admin/login/')
def api_recent_activity(request):
    """API для получения последней активности"""
    logs = AdminLog.objects.all().order_by('-created_at')[:5]
    
    activity = []
    for log in logs:
        activity.append({
            'admin': log.admin.username,
            'action': log.get_action_display(),
            'details': log.details,
            'timestamp': log.created_at.strftime('%Y-%m-%d %H:%M'),
            'company': log.target_company.name if log.target_company else None,
        })
    
    return JsonResponse({'activity': activity})

@user_passes_test(is_superuser_only, login_url='/admin/login/')
def admin_management(request):
    """Управление администраторами сайта (только для superuser)"""
    context = get_admin_context(request)
    site_admins = User.objects.filter(user_type='adminsite').select_related('employee')
    
    context.update({
        'site_admins': site_admins,
    })
    return render(request, 'admin_panel/admin_management.html', context)

@user_passes_test(is_superuser_only, login_url='/admin/login/')
def create_site_admin(request):
    """Создание нового администратора сайта"""
    context = get_admin_context(request)
    
    if request.method == 'POST':
        form = SiteAdminCreateForm(request.POST)
        if form.is_valid():
            try:
                admin = form.save()
                AdminLog.objects.create(
                    admin=request.user,
                    action='admin_created',
                    details=f'Создан администратор сайта: {admin.get_full_name()} ({admin.email})'
                )
                return redirect('admin_management')
            except Exception as e:
                pass
    else:
        form = SiteAdminCreateForm()
    
    context.update({
        'form': form,
        'title': 'Создание администратора сайта'
    })
    return render(request, 'admin_panel/admin_form.html', context)

@user_passes_test(is_superuser_only, login_url='/admin/login/')
def edit_site_admin(request, admin_id):
    """Редактирование администратора сайта"""
    context = get_admin_context(request)
    admin_user = get_object_or_404(User, id=admin_id, user_type='adminsite')
    
    try:
        admin_employee = Employee.objects.get(user=admin_user)
    except Employee.DoesNotExist:
        # Если записи Employee нет - создаем
        admin_employee = Employee.objects.create(
            user=admin_user,
            first_name=admin_user.first_name,
            last_name=admin_user.last_name,
            access_level='admin'
        )
    
    if request.method == 'POST':
        form = SiteAdminEditForm(request.POST, instance=admin_employee)
        if form.is_valid():
            try:
                admin = form.save()
                AdminLog.objects.create(
                    admin=request.user,
                    action='admin_updated',
                    details=f'Обновлен администратор сайта: {admin.user.get_full_name()} ({admin.user.email})'
                )
                return redirect('admin_management')
            except Exception as e:
                pass
    else:
        form = SiteAdminEditForm(instance=admin_employee)
    
    context.update({
        'form': form,
        'admin': admin_user,
        'title': 'Редактирование администратора сайта'
    })
    return render(request, 'admin_panel/admin_form.html', context)

@user_passes_test(is_superuser_only, login_url='/admin/login/')
def toggle_site_admin_status(request, admin_id):
    """Активация/деактивация администратора сайта"""
    admin_user = get_object_or_404(User, id=admin_id, user_type='adminsite')
    
    if admin_user == request.user:
        return redirect('admin_management')
    
    if admin_user.is_active:
        admin_user.is_active = False
        action = 'deactivated'
        message = f'✅ Администратор сайта {admin_user.get_full_name()} деактивирован'
    else:
        admin_user.is_active = True
        action = 'activated'
        message = f'✅ Администратор сайта {admin_user.get_full_name()} активирован'
    
    admin_user.save()
    
    AdminLog.objects.create(
        admin=request.user,
        action=f'admin_{action}',
        details=f'Администратор сайта {admin_user.get_full_name()} {action}'
    )
    
    return redirect('admin_management')

@user_passes_test(is_superuser_only, login_url='/admin/login/')
def delete_site_admin(request, admin_id):
    """Удаление администратора сайта"""
    admin_user = get_object_or_404(User, id=admin_id, user_type='adminsite')
    
    if admin_user == request.user:
        return redirect('admin_management')
    
    admin_name = admin_user.get_full_name()
    admin_email = admin_user.email
    
    admin_user.delete()
    
    AdminLog.objects.create(
        admin=request.user,
        action='admin_deleted',
        details=f'Удален администратор сайта: {admin_name} ({admin_email})'
    )
    
    return redirect('admin_management')


from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from django.http import HttpResponse
import json
from home.models import User, Company, Vacancy, Applicant, Employee, Response
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from openpyxl import Workbook
from django.views.decorators.http import require_http_methods

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from functools import wraps

def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):

        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        if request.user.user_type not in ['adminsite']:
            return HttpResponseForbidden("У вас нет прав для доступа к админ-панели")
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required, user_passes_test
import json
from datetime import datetime
from .statistics_service import StatisticsService

# Добавьте эти импорты для экспорта
import csv
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io

@login_required
@user_passes_test(is_admin)
def admin_statistics(request):
    """Страница статистики с поддержкой периода"""
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Валидация дат
    if start_date and end_date:
        try:
            start_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            if start_obj > end_obj:
                start_date, end_date = None, None
        except ValueError:
            start_date, end_date = None, None
    
    main_stats = StatisticsService.get_main_statistics(start_date, end_date)
    user_distribution = StatisticsService.get_user_type_distribution(start_date, end_date)
    vacancy_stats = StatisticsService.get_vacancy_statistics(start_date, end_date)
    company_stats = StatisticsService.get_company_statistics(start_date, end_date)
    response_stats = StatisticsService.get_response_statistics(start_date, end_date)
    complaint_stats = StatisticsService.get_complaint_statistics(start_date, end_date)
    
    # Подготавливаем данные для круговых диаграмм
    user_chart_data = []
    cumulative_percent = 0
    for i, (label, count, percentage, color) in enumerate(zip(
        user_distribution['labels'],
        user_distribution['data'], 
        user_distribution['percentages'],
        user_distribution['colors']
    )):
        dash_length = percentage
        gap_length = 100 - percentage
        dash_offset = -cumulative_percent
        
        user_chart_data.append({
            'label': label,
            'count': count,
            'percentage': percentage,
            'color': color,
            'dash_array': f"{dash_length} {gap_length}",
            'dash_offset': dash_offset
        })
        cumulative_percent += percentage
    
    company_chart_data = []
    cumulative_percent = 0
    for i, (label, count, percentage, color) in enumerate(zip(
        company_stats['status_distribution']['labels'],
        company_stats['status_distribution']['data'],
        company_stats['status_distribution']['percentages'],
        company_stats['status_distribution']['colors']
    )):
        dash_length = percentage
        gap_length = 100 - percentage
        dash_offset = -cumulative_percent
        
        company_chart_data.append({
            'label': label,
            'count': count,
            'percentage': percentage,
            'color': color,
            'dash_array': f"{dash_length} {gap_length}",
            'dash_offset': dash_offset
        })
        cumulative_percent += percentage
    
    response_chart_data = []
    cumulative_percent = 0
    response_total = response_stats['status_distribution']['total']
    for i, (label, count, color) in enumerate(zip(
        response_stats['status_distribution']['labels'],
        response_stats['status_distribution']['data'],
        response_stats['status_distribution']['colors']
    )):
        percentage = round((count / response_total * 100), 1) if response_total > 0 else 0
        dash_length = percentage
        gap_length = 100 - percentage
        dash_offset = -cumulative_percent
        
        response_chart_data.append({
            'label': label,
            'count': count,
            'percentage': percentage,
            'color': color,
            'dash_array': f"{dash_length} {gap_length}",
            'dash_offset': dash_offset
        })
        cumulative_percent += percentage
    
    # Подготавливаем данные для столбчатых диаграмм
    vacancy_data = []
    if vacancy_stats['category']['data']:
        max_count = max(vacancy_stats['category']['data']) if vacancy_stats['category']['data'] else 1
        for label, count, color in zip(
            vacancy_stats['category']['labels'],
            vacancy_stats['category']['data'],
            vacancy_stats['category']['colors']
        ):
            if max_count > 0:
                height = (count / max_count) * 80
            else:
                height = 5
            vacancy_data.append((label, count, color, max(height, 5)))
    
    complaint_data = []
    if complaint_stats['type_distribution']['data']:
        max_count = max(complaint_stats['type_distribution']['data']) if complaint_stats['type_distribution']['data'] else 1
        for label, count, color in zip(
            complaint_stats['type_distribution']['labels'],
            complaint_stats['type_distribution']['data'],
            complaint_stats['type_distribution']['colors']
        ):
            if max_count > 0:
                height = (count / max_count) * 80
            else:
                height = 5
            complaint_data.append((label, count, color, max(height, 5)))
    
    response_daily_data = []
    if response_stats['daily_activity']:
        daily_counts = [day['count'] for day in response_stats['daily_activity']]
        max_count = max(daily_counts) if daily_counts else 1
        for day in response_stats['daily_activity']:
            if max_count > 0:
                height = (day['count'] / max_count) * 80
            else:
                height = 5
            response_daily_data.append((day['date'], day['count'], max(height, 5)))
    
    context = {
        'main_stats': main_stats,
        'user_total': user_distribution['total'],
        'company_total': company_stats['status_distribution']['total'],
        'response_total': response_stats['status_distribution']['total'],
        
        'user_chart_data': user_chart_data,
        'company_chart_data': company_chart_data,
        'response_chart_data': response_chart_data,
        
        'vacancy_data': vacancy_data,
        'complaint_data': complaint_data,
        'response_daily_data': response_daily_data,
        
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return render(request, 'admin_panel/statistics.html', context)

from reportlab.platypus import Image
from reportlab.lib.units import inch

@login_required
@user_passes_test(is_admin)
def export_statistics_pdf(request):
    """Экспорт статистики в PDF с поддержкой периода"""
    try:
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Валидация дат
        if start_date and end_date:
            try:
                start_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                if start_obj > end_obj:
                    start_date, end_date = None, None
            except ValueError:
                start_date, end_date = None, None
        
        # Собираем данные с учетом периода
        main_stats = StatisticsService.get_main_statistics(start_date, end_date)
        user_distribution = StatisticsService.get_user_type_distribution(start_date, end_date)
        vacancy_stats = StatisticsService.get_vacancy_statistics(start_date, end_date)
        company_stats = StatisticsService.get_company_statistics(start_date, end_date)
        response_stats = StatisticsService.get_response_statistics(start_date, end_date)
        complaint_stats = StatisticsService.get_complaint_statistics(start_date, end_date)
        
        # Создаем PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=30)
        elements = []
        
        # Регистрируем шрифты
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.fonts import addMapping
        
        font_name = 'Times-Roman'
        bold_font_name = 'Times-Bold'
        
        try:
            # Пробуем найти и зарегистрировать Times New Roman
            font_variants = [
                'times.ttf', 'timesbd.ttf', 'timesi.ttf', 'timesbi.ttf',
                'Times New Roman.ttf', 'Times New Roman Bold.ttf',
                '/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf',
                '/Library/Fonts/Times New Roman.ttf',
            ]
            
            for font_variant in font_variants:
                try:
                    if 'timesbd' in font_variant or 'Bold' in font_variant:
                        pdfmetrics.registerFont(TTFont('TimesNewRoman-Bold', font_variant))
                        bold_font_name = 'TimesNewRoman-Bold'
                    else:
                        pdfmetrics.registerFont(TTFont('TimesNewRoman', font_variant))
                        font_name = 'TimesNewRoman'
                except:
                    continue
            
            if font_name == 'TimesNewRoman' and bold_font_name == 'TimesNewRoman-Bold':
                addMapping('TimesNewRoman', 0, 0, 'TimesNewRoman')
                addMapping('TimesNewRoman', 1, 0, 'TimesNewRoman-Bold')
            else:
                font_name = 'Times-Roman'
                bold_font_name = 'Times-Bold'
                
        except Exception as e:
            print(f"Font registration error: {e}")
            font_name = 'Times-Roman'
            bold_font_name = 'Times-Bold'
        
        # Стили
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=bold_font_name,
            fontSize=16,
            spaceAfter=30,
            alignment=1
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontName=bold_font_name,
            fontSize=12,
            spaceAfter=12
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontName=font_name,
            fontSize=10
        )
        
        # Заголовок
        title = Paragraph("Статистика платформы трудоустройства", title_style)
        elements.append(title)
        
        period_info = f"Дата экспорта: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        if start_date and end_date:
            period_info += f" | Период: {start_date} - {end_date}"
        
        elements.append(Paragraph(period_info, normal_style))
        elements.append(Spacer(1, 20))
        
        # Основная статистика
        elements.append(Paragraph("Основная статистика", heading_style))
        
        main_data = [
            ['Показатель', 'Значение'],
            ['Всего пользователей', str(main_stats['total_users'])],
            ['Всего компаний', str(main_stats['total_companies'])],
            ['Всего вакансий', str(main_stats['total_vacancies'])],
            ['Всего откликов', str(main_stats['total_responses'])],
            ['Активных компаний', str(main_stats['active_companies'])],
        ]
        
        # Добавляем информацию о периоде, если он указан
        if not start_date or not end_date:
            main_data.extend([
                ['Новых пользователей (неделя)', str(main_stats['new_users_week'])],
                ['Новых компаний (неделя)', str(main_stats['new_companies_week'])],
                ['Новых вакансий (неделя)', str(main_stats['new_vacancies_week'])],
            ])
        
        main_table = Table(main_data, colWidths=[250, 100])
        main_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), bold_font_name),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(main_table)
        elements.append(Spacer(1, 20))
        
        # Остальные графики и таблицы (аналогично вашему коду)
        # График распределения пользователей
        elements.append(Paragraph("Распределение пользователей по типам", heading_style))
        user_chart_buffer = create_user_distribution_chart(user_distribution)
        if user_chart_buffer:
            user_chart = Image(user_chart_buffer, width=6*inch, height=4*inch)
            elements.append(user_chart)
        elements.append(Spacer(1, 10))
        
        # Таблица распределения пользователей
        user_data = [['Тип пользователя', 'Количество', 'Процент']]
        for i, label in enumerate(user_distribution['labels']):
            user_data.append([
                label,
                str(user_distribution['data'][i]),
                f"{user_distribution['percentages'][i]}%"
            ])
        
        user_table = Table(user_data, colWidths=[200, 80, 80])
        user_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), bold_font_name),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(user_table)
        elements.append(Spacer(1, 20))
        
        # График статусов компаний
        elements.append(Paragraph("Статусы компаний", heading_style))
        company_chart_buffer = create_company_status_chart(company_stats)
        if company_chart_buffer:
            company_chart = Image(company_chart_buffer, width=6*inch, height=4*inch)
            elements.append(company_chart)
        elements.append(Spacer(1, 10))
        
        # Таблица статусов компаний
        company_data = [['Статус', 'Количество', 'Процент']]
        for i, label in enumerate(company_stats['status_distribution']['labels']):
            company_data.append([
                label,
                str(company_stats['status_distribution']['data'][i]),
                f"{company_stats['status_distribution']['percentages'][i]}%"
            ])
        
        company_table = Table(company_data, colWidths=[200, 80, 80])
        company_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), bold_font_name),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(company_table)
        elements.append(Spacer(1, 20))
        
        # График категорий вакансий
        elements.append(Paragraph("Категории вакансий", heading_style))
        vacancy_chart_buffer = create_vacancy_categories_chart(vacancy_stats)
        if vacancy_chart_buffer:
            vacancy_chart = Image(vacancy_chart_buffer, width=6*inch, height=4*inch)
            elements.append(vacancy_chart)
        elements.append(Spacer(1, 10))
        
        # Таблица категорий вакансий
        vacancy_data = [['Категория', 'Количество']]
        for i, label in enumerate(vacancy_stats['category']['labels']):
            vacancy_data.append([
                label,
                str(vacancy_stats['category']['data'][i])
            ])
        
        vacancy_table = Table(vacancy_data, colWidths=[200, 80])
        vacancy_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), bold_font_name),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(vacancy_table)
        elements.append(Spacer(1, 20))
        
        # График активности откликов
        elements.append(Paragraph("Активность откликов", heading_style))
        response_chart_buffer = create_response_activity_chart(response_stats)
        if response_chart_buffer:
            response_chart = Image(response_chart_buffer, width=6*inch, height=4*inch)
            elements.append(response_chart)
        
        # Собираем PDF
        doc.build(elements)
        
        # Возвращаем файл
        buffer.seek(0)
        filename = "statistics"
        if start_date and end_date:
            filename += f"_{start_date}_to_{end_date}"
        filename += f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        return HttpResponse(f"Ошибка при создании PDF: {str(e)}")

@login_required
@user_passes_test(is_admin)
def export_statistics_excel(request):
    """Экспорт статистики в Excel (CSV) с поддержкой периода"""
    try:
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Валидация дат
        if start_date and end_date:
            try:
                start_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                if start_obj > end_obj:
                    start_date, end_date = None, None
            except ValueError:
                start_date, end_date = None, None
        
        # Собираем данные с учетом периода
        main_stats = StatisticsService.get_main_statistics(start_date, end_date)
        user_distribution = StatisticsService.get_user_type_distribution(start_date, end_date)
        vacancy_stats = StatisticsService.get_vacancy_statistics(start_date, end_date)
        company_stats = StatisticsService.get_company_statistics(start_date, end_date)
        response_stats = StatisticsService.get_response_statistics(start_date, end_date)
        complaint_stats = StatisticsService.get_complaint_statistics(start_date, end_date)
        
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        
        filename = "statistics"
        if start_date and end_date:
            filename += f"_{start_date}_to_{end_date}"
        filename += f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Создаем CSV writer с поддержкой русского
        writer = csv.writer(response)
        
        # Заголовок
        writer.writerow(['Статистика платформы трудоустройства'])
        period_info = f"Дата экспорта: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        if start_date and end_date:
            period_info += f" | Период: {start_date} - {end_date}"
        writer.writerow([period_info])
        writer.writerow([])
        
        # Основная статистика
        writer.writerow(['ОСНОВНАЯ СТАТИСТИКА'])
        writer.writerow(['Показатель', 'Значение'])
        writer.writerow(['Всего пользователей', main_stats['total_users']])
        writer.writerow(['Всего компаний', main_stats['total_companies']])
        writer.writerow(['Всего вакансий', main_stats['total_vacancies']])
        writer.writerow(['Всего откликов', main_stats['total_responses']])
        writer.writerow(['Активных компаний', main_stats['active_companies']])
        
        if not start_date or not end_date:
            writer.writerow(['Новых пользователей (неделя)', main_stats['new_users_week']])
            writer.writerow(['Новых компаний (неделя)', main_stats['new_companies_week']])
            writer.writerow(['Новых вакансий (неделя)', main_stats['new_vacancies_week']])
        
        writer.writerow([])
        
        # Распределение пользователей
        writer.writerow(['РАСПРЕДЕЛЕНИЕ ПОЛЬЗОВАТЕЛЕЙ ПО ТИПАМ'])
        writer.writerow(['Тип пользователя', 'Количество', 'Процент'])
        for i, label in enumerate(user_distribution['labels']):
            writer.writerow([
                label,
                user_distribution['data'][i],
                f"{user_distribution['percentages'][i]}%"
            ])
        writer.writerow([])
        
        # Статусы компаний
        writer.writerow(['СТАТУСЫ КОМПАНИЙ'])
        writer.writerow(['Статус', 'Количество', 'Процент'])
        for i, label in enumerate(company_stats['status_distribution']['labels']):
            writer.writerow([
                label,
                company_stats['status_distribution']['data'][i],
                f"{company_stats['status_distribution']['percentages'][i]}%"
            ])
        writer.writerow([])
        
        # Категории вакансий
        writer.writerow(['КАТЕГОРИИ ВАКАНСИЙ'])
        writer.writerow(['Категория', 'Количество'])
        for i, label in enumerate(vacancy_stats['category']['labels']):
            writer.writerow([label, vacancy_stats['category']['data'][i]])
        writer.writerow([])
        
        # Активность откликов
        writer.writerow(['АКТИВНОСТЬ ОТКЛИКОВ'])
        writer.writerow(['Дата', 'Количество откликов'])
        for day in response_stats['daily_activity']:
            writer.writerow([day['date'], day['count']])
        writer.writerow([])
        
        # Типы жалоб
        writer.writerow(['ТИПЫ ЖАЛОБ'])
        writer.writerow(['Тип жалобы', 'Количество'])
        for i, label in enumerate(complaint_stats['type_distribution']['labels']):
            writer.writerow([label, complaint_stats['type_distribution']['data'][i]])
        
        return response
        
    except Exception as e:
        return HttpResponse(f"Ошибка при создании Excel: {str(e)}")

# Функции для создания графиков (остаются без изменений)
def create_user_distribution_chart(user_distribution):
    """Создает круговую диаграмму распределения пользователей"""
    try:
        plt.figure(figsize=(8, 6))
        plt.pie(
            user_distribution['data'],
            labels=user_distribution['labels'],
            colors=user_distribution['colors'],
            autopct='%1.1f%%',
            startangle=90
        )
        plt.title('Распределение пользователей по типам', fontsize=14, fontweight='bold')
        plt.axis('equal')
        
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        plt.close()
        return buffer
    except Exception as e:
        print(f"Ошибка при создании графика пользователей: {e}")
        return None

def create_company_status_chart(company_stats):
    """Создает круговую диаграмму статусов компаний"""
    try:
        plt.figure(figsize=(8, 6))
        plt.pie(
            company_stats['status_distribution']['data'],
            labels=company_stats['status_distribution']['labels'],
            colors=company_stats['status_distribution']['colors'],
            autopct='%1.1f%%',
            startangle=90
        )
        plt.title('Статусы компаний', fontsize=14, fontweight='bold')
        plt.axis('equal')
        
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        plt.close()
        return buffer
    except Exception as e:
        print(f"Ошибка при создании графика компаний: {e}")
        return None

def create_vacancy_categories_chart(vacancy_stats):
    """Создает столбчатую диаграмму категорий вакансий"""
    try:
        plt.figure(figsize=(10, 6))
        bars = plt.bar(
            vacancy_stats['category']['labels'],
            vacancy_stats['category']['data'],
            color=vacancy_stats['category']['colors']
        )
        plt.title('Категории вакансий', fontsize=14, fontweight='bold')
        plt.xlabel('Категории')
        plt.ylabel('Количество вакансий')
        plt.xticks(rotation=45, ha='right')
        
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}',
                    ha='center', va='bottom')
        
        plt.tight_layout()
        
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        plt.close()
        return buffer
    except Exception as e:
        print(f"Ошибка при создании графика вакансий: {e}")
        return None

def create_response_activity_chart(response_stats):
    """Создает линейный график активности откликов"""
    try:
        dates = [day['date'] for day in response_stats['daily_activity']]
        counts = [day['count'] for day in response_stats['daily_activity']]
        
        plt.figure(figsize=(10, 6))
        plt.plot(dates, counts, marker='o', linewidth=2, markersize=6)
        plt.title('Активность откликов', fontsize=14, fontweight='bold')
        plt.xlabel('Дата')
        plt.ylabel('Количество откликов')
        plt.grid(True, alpha=0.3)
        
        for i, count in enumerate(counts):
            plt.annotate(str(count), (dates[i], count), 
                        textcoords="offset points", 
                        xytext=(0,10), 
                        ha='center')
        
        plt.tight_layout()
        
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        plt.close()
        return buffer
    except Exception as e:
        print(f"Ошибка при создании графика откликов: {e}")
        return None
    
from django.core.paginator import Paginator
@login_required
@admin_required
def admin_complaints(request):
    # Получаем параметры фильтрации
    status_filter = request.GET.get('status', 'all')
    type_filter = request.GET.get('type', 'all')
    
    # Базовый запрос
    complaints = Complaint.objects.select_related(
        'vacancy', 'vacancy__company', 'complainant'
    ).order_by('-created_at')
    
    # Применяем фильтры
    if status_filter != 'all':
        complaints = complaints.filter(status=status_filter)
    
    if type_filter != 'all':
        complaints = complaints.filter(complaint_type=type_filter)
    
    # Пагинация
    paginator = Paginator(complaints, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Статистика для бокового меню
    pending_complaints_count = Complaint.objects.filter(status='pending').count()
    
    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'pending_complaints_count': pending_complaints_count,
        'total_complaints': complaints.count(),
        'pending_count': Complaint.objects.filter(status='pending').count(),
        'resolved_count': Complaint.objects.filter(status='resolved').count(),
    }
    
    return render(request, 'admin_panel/complaints.html', context)

@admin_required
def complaint_detail(request, complaint_id):
    complaint = get_object_or_404(
        Complaint.objects.select_related(
            'vacancy', 
            'vacancy__company', 
            'complainant',
            'vacancy__work_conditions'
        ), 
        id=complaint_id
    )
    
    # Получаем статистику для бокового меню
    pending_complaints_count = Complaint.objects.filter(status='pending').count()
    pending_companies_count = Company.objects.filter(status='pending').count()
    
    context = {
        'complaint': complaint,
        'pending_complaints_count': pending_complaints_count,
        'pending_companies_count': pending_companies_count,
    }
    
    return render(request, 'admin_panel/complaint_detail.html', context)

@admin_required
@user_passes_test(is_admin, login_url='/admin/login/')
def update_complaint_status(request, complaint_id):
    if request.method == 'POST':
        complaint = get_object_or_404(Complaint, id=complaint_id)
        new_status = request.POST.get('status')
        admin_notes = request.POST.get('admin_notes', '')
        
        if new_status in dict(Complaint.STATUS_CHOICES):
            old_status = complaint.status
            complaint.status = new_status
            complaint.admin_notes = admin_notes
            complaint.resolved_at = timezone.now() if new_status in ['resolved', 'rejected'] else None
            complaint.save()
            
            AdminLog.objects.create(
                admin=request.user,
                action='complaint_updated',
                details=f'Изменен статус жалобы #{complaint.id} с "{dict(Complaint.STATUS_CHOICES).get(old_status)}" на "{complaint.get_status_display()}"'
            )
            
            messages.success(request, f'Статус жалобы обновлен на "{complaint.get_status_display()}"')
        else:
            messages.error(request, 'Неверный статус')
    
    return redirect('complaint_detail', complaint_id=complaint_id)

def send_vacancy_archive_email(vacancy, archive_reason=""):
    """
    Отправляет email уведомление компании при архивации вакансии
    """
    company_email = vacancy.company.user.email
    company_name = vacancy.company.name
    vacancy_title = vacancy.position
    
    try:
        subject = f'Вакансия "{vacancy_title}" перемещена в архив - HR-Lab'
        
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
                    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
                    color: white;
                    padding: 40px 30px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                    font-weight: 700;
                }}
                .header p {{
                    margin: 10px 0 0 0;
                    opacity: 0.9;
                    font-size: 16px;
                }}
                .content {{
                    padding: 40px 30px;
                }}
                .warning-card {{
                    background: rgba(245, 158, 11, 0.05);
                    border: 2px solid rgba(245, 158, 11, 0.3);
                    border-radius: 15px;
                    padding: 25px;
                    margin: 25px 0;
                    text-align: center;
                }}
                .warning-icon {{
                    font-size: 48px;
                    margin-bottom: 15px;
                }}
                .warning-title {{
                    font-size: 20px;
                    font-weight: 700;
                    color: #92400e;
                    margin-bottom: 10px;
                }}
                .warning-description {{
                    color: #92400e;
                    font-size: 16px;
                    line-height: 1.5;
                }}
                .vacancy-info {{
                    background: #f8fafc;
                    border-radius: 12px;
                    padding: 20px;
                    margin: 25px 0;
                }}
                .info-item {{
                    display: flex;
                    justify-content: space-between;
                    padding: 10px 0;
                    border-bottom: 1px solid #e2e8f0;
                }}
                .info-item:last-child {{
                    border-bottom: none;
                }}
                .info-label {{
                    color: #64748b;
                    font-weight: 500;
                }}
                .info-value {{
                    color: #1e293b;
                    font-weight: 600;
                }}
                .reason-section {{
                    background: rgba(239, 68, 68, 0.05);
                    border: 1px solid rgba(239, 68, 68, 0.2);
                    border-radius: 12px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .reason-title {{
                    color: #dc2626;
                    font-weight: 600;
                    margin-bottom: 10px;
                }}
                .action-buttons {{
                    text-align: center;
                    margin: 30px 0;
                }}
                .action-button {{
                    display: inline-block;
                    background: linear-gradient(45deg, #2563eb, #1e40af);
                    color: white;
                    padding: 14px 32px;
                    text-decoration: none;
                    border-radius: 25px;
                    font-weight: 600;
                    font-size: 16px;
                    margin: 10px;
                    transition: all 0.3s ease;
                }}
                .action-button:hover {{
                    background: linear-gradient(45deg, #1e40af, #2563eb);
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(37, 99, 235, 0.3);
                }}
                .secondary-button {{
                    background: linear-gradient(45deg, #64748b, #475569);
                }}
                .secondary-button:hover {{
                    background: linear-gradient(45deg, #475569, #64748b);
                }}
                .footer {{
                    background: #f1f5f9;
                    padding: 30px;
                    text-align: center;
                    border-top: 1px solid #e2e8f0;
                }}
                .footer p {{
                    margin: 5px 0;
                    color: #64748b;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📋 HR-Lab</h1>
                    <p>Уведомление об архивации вакансии</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #1e293b; margin-top: 0;">Уважаемый представитель компании {company_name}!</h2>
                    
                    <div class="warning-card">
                        <div class="warning-icon">📁</div>
                        <div class="warning-title">Вакансия перемещена в архив</div>
                        <div class="warning-description">
                            Ваша вакансия "<strong>{vacancy_title}</strong>" была перемещена в архив модератором платформы.
                        </div>
                    </div>
                    
                    <div class="vacancy-info">
                        <div class="info-item">
                            <span class="info-label">Вакансия:</span>
                            <span class="info-value">{vacancy_title}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">Компания:</span>
                            <span class="info-value">{company_name}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">Дата архивации:</span>
                            <span class="info-value">{timezone.now().strftime('%d.%m.%Y в %H:%M')}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">Статус:</span>
                            <span class="info-value" style="color: #f59e0b; font-weight: 700;">Архивирована</span>
                        </div>
                    </div>
                    
                    {f'''
                    <div class="reason-section">
                        <div class="reason-title">📝 Причина архивации:</div>
                        <p style="color: #1e293b; margin: 0; line-height: 1.5;">{archive_reason}</p>
                    </div>
                    ''' if archive_reason else ''}
                    
                    <div class="action-buttons">
                        <p style="color: #64748b; margin-bottom: 20px;">
                            Вы можете создать новую вакансию или связаться с поддержкой для уточнения деталей.
                        </p>
                        <a href="http://127.0.0.1:8000/create_vacancy/" class="action-button">
                            📝 Создать новую вакансию
                        </a>
                        <a href="http://127.0.0.1:8000/contact/" class="action-button secondary-button">
                            📞 Связаться с поддержкой
                        </a>
                    </div>
                    
                    <p style="color: #64748b; font-size: 14px; text-align: center;">
                        <strong>Важно:</strong> Архивные вакансии не отображаются в поиске и не получают откликов от соискателей.
                    </p>
                </div>
                
                <div class="footer">
                    <p><strong>С уважением, команда HR-Lab</strong></p>
                    <p>Мы заботимся о качестве вакансий на нашей платформе</p>
                    <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e2e8f0;">
                        <p>Email: hr-labogency@mail.ru</p>
                    </div>
                    <p style="font-size: 12px; margin-top: 20px; color: #94a3b8;">
                        Это автоматическое сообщение, пожалуйста, не отвечайте на него.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Текстовая версия
        plain_message = f"""
        Уважаемый представитель компании "{company_name}"!

        Ваша вакансия "{vacancy_title}" была перемещена в архив модератором платформы HR-Lab.

        Информация о вакансии:
        - Вакансия: {vacancy_title}
        - Компания: {company_name}
        - Дата архивации: {timezone.now().strftime('%d.%m.%Y в %H:%M')}
        - Статус: Архивирована

        {f'Причина архивации: {archive_reason}' if archive_reason else ''}

        Важно: Архивные вакансии не отображаются в поиске и не получают откликов от соискателей.

        Вы можете:
        - Создать новую вакансию: http://127.0.0.1:8000/create_vacancy/
        - Связаться с поддержкой: http://127.0.0.1:8000/contact/

        С уважением,
        Команда HR-Lab

        ---
        Email: hr-labogency@mail.ru
        """

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[company_email],
            html_message=html_message,
            fail_silently=False,
        )
        
        print(f"✅ [EMAIL] Уведомление об архивации отправлено для {vacancy_title}")
        return True
        
    except Exception as e:
        print(f"❌ [EMAIL] ОШИБКА при отправке уведомления об архивации: {str(e)}")
        return False
    
@admin_required
@user_passes_test(is_admin, login_url='/admin/login/')
def archive_vacancy(request, vacancy_id):
    """
    Архивация вакансии с отправкой email уведомления
    """
    vacancy = get_object_or_404(Vacancy, id=vacancy_id)
    
    try:
        archived_status = StatusVacancies.objects.get(status_vacancies_name='Архивирована')
    except StatusVacancies.DoesNotExist:
        messages.error(request, 'Статус "Архивирована" не найден в системе.')
        return redirect('admin_complaints')
    
    if request.method == 'POST':
        archive_reason = request.POST.get('archive_reason', '')
        
        # Сохраняем старый статус для лога
        old_status = vacancy.status.status_vacancies_name
        
        # Обновляем статус вакансии
        vacancy.status = archived_status
        vacancy.archived_at = timezone.now()
        vacancy.archive_reason = archive_reason
        vacancy.save()
        
        # Отправляем email уведомление
        email_sent = send_vacancy_archive_email(vacancy, archive_reason)
        
        # Создаем лог действия
        AdminLog.objects.create(
            admin=request.user,
            action='vacancy_archived',
            target_company=vacancy.company,
            details=f'Вакансия "{vacancy.position}" архивирована. Причина: {archive_reason or "Не указана"}. Email отправлен: {"Да" if email_sent else "Нет"}'
        )
        
        if email_sent:
            messages.success(request, f'Вакансия "{vacancy.position}" архивирована. Email уведомление отправлено компании.')
        else:
            messages.warning(request, f'Вакансия "{vacancy.position}" архивирована, но не удалось отправить email уведомление.')
        
        return redirect('admin_complaints')
    
    # GET запрос - показываем форму подтверждения
    return render(request, 'admin_panel/confirm_archive.html', {
        'vacancy': vacancy,
        'pending_complaints_count': Complaint.objects.filter(status='pending').count(),
        'pending_companies_count': Company.objects.filter(status='pending').count(),
    })

@admin_required
def unarchive_vacancy(request, vacancy_id):
    """
    Восстановление вакансии из архива
    """
    vacancy = get_object_or_404(Vacancy, id=vacancy_id)
    
    # Получаем активный статус (предположим, что он называется "Активная")
    try:
        active_status = StatusVacancies.objects.get(status_vacancies_name='Активная')
    except StatusVacancies.DoesNotExist:
        # Если нет "Активной", берем первый доступный статус кроме архивного
        active_status = StatusVacancies.objects.exclude(status_vacancies_name='Архивирована').first()
    
    if vacancy.status.status_vacancies_name == 'Архивирована':
        vacancy.status = active_status
        vacancy.archived_at = None
        vacancy.archive_reason = ''
        vacancy.save()
        
        # Создаем лог действия
        AdminLog.objects.create(
            admin=request.user,
            action='vacancy_unarchived',
            target_company=vacancy.company,
            details=f'Вакансия "{vacancy.position}" восстановлена из архива'
        )
        
        messages.success(request, f'Вакансия "{vacancy.position}" восстановлена из архива.')
    
    return redirect('admin_complaints')

@login_required
def admin_profile(request):
    """Профиль администратора"""
    # Получаем статистику для отображения
    total_users = User.objects.count()
    total_companies = Company.objects.count()
    total_vacancies = Vacancy.objects.count()
    pending_complaints = Complaint.objects.filter(status='pending').count()
    pending_companies_count = Company.objects.filter(status='pending').count()
    pending_complaints_count = Complaint.objects.filter(status='pending').count()
    
    # Получаем последние действия (пример)
    recent_activity = [
        {
            'icon': 'user-check',
            'description': 'Одобрена компания "ТехноПарк"',
            'timestamp': timezone.now() - timedelta(hours=2)
        },
        {
            'icon': 'flag',
            'description': 'Рассмотрена жалоба на вакансию',
            'timestamp': timezone.now() - timedelta(hours=4)
        },
        {
            'icon': 'database',
            'description': 'Создан резервный бэкап',
            'timestamp': timezone.now() - timedelta(days=1)
        }
    ]
    
    context = {
        'total_users': total_users,
        'total_companies': total_companies,
        'total_vacancies': total_vacancies,
        'pending_complaints': pending_complaints,
        'pending_companies_count': pending_companies_count,
        'pending_complaints_count': pending_complaints_count,
        'recent_activity': recent_activity,
    }
    
    return render(request, 'admin_panel/admin_profile.html', context)


@login_required
def admin_profile_edit(request):
    """Редактирование профиля администратора"""
    if request.method == 'POST':
        form = AdminProfileEditForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль успешно обновлен!')
            return redirect('admin_profile')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = AdminProfileEditForm(instance=request.user)
    
    # Статистика для сайдбара
    pending_companies_count = Company.objects.filter(status='pending').count()
    pending_complaints_count = Complaint.objects.filter(status='pending').count()
    
    context = {
        'form': form,
        'pending_companies_count': pending_companies_count,
        'pending_complaints_count': pending_complaints_count,
    }
    
    return render(request, 'admin_panel/admin_profile_edit.html', context)