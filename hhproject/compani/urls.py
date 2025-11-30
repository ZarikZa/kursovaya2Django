from django.urls import path
from .views import *

urlpatterns = [
    path('', home_comp, name='home_comp'),
    path('register/', CompanyRegisterView.as_view(), name='reg_comp'),
    path('profile/', company_profile, name='company_profile'),
    path('edit-profile/', edit_company_profile, name='edit_company_profile'),
    path('company/verify-password/', verify_password_and_save, name='verify_password_and_save'),
    path('change-password/', change_password_request, name='change_password_request'),
    path('change-password/<str:uidb64>/<str:token>/', change_password_confirm, name='change_password_confirm'),
    path('hr-agents/', hr_agents_list, name='hr_agents_list'),
    path('hr-agents/create/', hr_agent_create, name='hr_agent_create'),
    path('hr-agents/edit/<int:employee_id>/', hr_agent_edit, name='hr_agent_edit'),
    path('create-vacancy/', create_vacancy, name='create_vacancy'),
    path('vacancies/', vacancy_list, name='vacancy_list'),
    path('edit-vacancy/<int:vacancy_id>/', edit_vacancy, name='edit_vacancy'),
    path('archive-vacancy/<int:vacancy_id>/', archive_vacancy, name='archive_vacancy'),
    path('unarchive-vacancy/<int:vacancy_id>/', unarchive_vacancy, name='unarchive_vacancy'),
    path('responses/', responses_list, name='responses_list'),
    path('account/pending/', account_pending, name='account_pending'),
    path('vacancy/<int:vacancy_id>/edit/', edit_vacancy, name='edit_vacancy'),
    path('employee/profile/', employee_profile, name='employee_profile'),
    path('employee/profile/edit/', edit_employee_profile, name='edit_employee_profile'),
    path('delete/', delete_company_profile, name='delete_company_profile'),
    path('hr-agents/export/', export_hr_agents_csv, name='export_hr_agents_csv'),
    path('hr-agents/import/', import_hr_agents, name='import_hr_agents'),
]