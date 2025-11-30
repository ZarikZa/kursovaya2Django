from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('companies', views.CompanyViewSet)
router.register('vacancies', views.VacancyViewSet)
router.register('applicants', views.ApplicantViewSet)
router.register('employees', views.EmployeeViewSet)
router.register('complaints', views.ComplaintViewSet)
router.register('responses', views.ResponseViewSet)
router.register('favorites', views.FavoritesViewSet)
router.register('work-conditions', views.WorkConditionsViewSet)
router.register('status-vacancies', views.StatusVacanciesViewSet)
router.register('status-responses', views.StatusResponseViewSet)
router.register('admin-logs', views.AdminLogViewSet)
router.register('backups', views.BackupViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
]