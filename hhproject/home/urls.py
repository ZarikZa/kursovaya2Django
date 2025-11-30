
from django.urls import path
from django.urls import path, include
from .views import *
from compani.views import *

urlpatterns = [
    path('', home_page, name='home_page'),
    path('vakansii/', vakansii_page, name='vakansi_page'),
    path('registration/', ApplicantRegisterView.as_view(), name='registration_user'),
    path('login/', custom_login, name='login_user'),
    path('logout/', custom_logout, name='logout'),
    path('compani/', home_comp, name='home_comp'),
    path('profile/', applicant_profile, name='applicant_profile'),
    path('vacancy/<int:vacancy_id>/', vacancy_detail, name='vacancy_detail'),  
    path('vacancy/<int:vacancy_id>/apply/', apply_to_vacancy, name='apply_to_vacancy'),
    path('vacancy/<int:vacancy_id>/add_to_favorites/', add_to_favorites, name='add_to_favorites'),
    path('vacancy/<int:vacancy_id>/remove_from_favorites/', remove_from_favorites, name='remove_from_favorites'),
    path('profile/edit/', edit_applicant_profile, name='edit_applicant_profile'),
    path('profile/delete/', delete_applicant_profile, name='delete_applicant_profile'),
    path('password-reset/', password_reset_request, name='password_reset_request'),
    path('password-reset/verify/', password_reset_verify, name='password_reset_verify'),
    path('password-reset/new/', password_reset_new, name='password_reset_new'),
    path('update-theme/', update_theme, name='update_theme'),
    path('vacancy/<int:vacancy_id>/complaint/', create_complaint, name='create_complaint'),
    path('vacancy/<int:vacancy_id>/complaint/success/', complaint_success, name='complaint_success'),
    path('vacancy/<int:vacancy_id>/check-complaint/', check_existing_complaint, name='check_complaint'),
    path('update-metrics/', send_metrics, name='update_metrics'),
]   