from rest_framework import viewsets
from rest_framework.response import Response
from .permissions import IsSuperUser
from .serializers import *

class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [IsSuperUser]

class VacancyViewSet(viewsets.ModelViewSet):
    queryset = Vacancy.objects.all()
    permission_classes = [IsSuperUser]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return VacancyListSerializer
        return VacancyDetailSerializer

class ApplicantViewSet(viewsets.ModelViewSet):
    queryset = Applicant.objects.all()
    serializer_class = ApplicantSerializer
    permission_classes = [IsSuperUser]

class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsSuperUser]

class ComplaintViewSet(viewsets.ModelViewSet):
    queryset = Complaint.objects.all()
    serializer_class = ComplaintSerializer
    permission_classes = [IsSuperUser]

class ResponseViewSet(viewsets.ModelViewSet):
    queryset = Response.objects.all()
    serializer_class = ResponseSerializer
    permission_classes = [IsSuperUser]

class FavoritesViewSet(viewsets.ModelViewSet):
    queryset = Favorites.objects.all()
    serializer_class = FavoritesSerializer
    permission_classes = [IsSuperUser]

class WorkConditionsViewSet(viewsets.ModelViewSet):
    queryset = WorkConditions.objects.all()
    serializer_class = WorkConditionsSerializer
    permission_classes = [IsSuperUser]

class StatusVacanciesViewSet(viewsets.ModelViewSet):
    queryset = StatusVacancies.objects.all()
    serializer_class = StatusVacanciesSerializer
    permission_classes = [IsSuperUser]

class StatusResponseViewSet(viewsets.ModelViewSet):
    queryset = StatusResponse.objects.all()
    serializer_class = StatusResponseSerializer
    permission_classes = [IsSuperUser]

class AdminLogViewSet(viewsets.ModelViewSet):
    queryset = AdminLog.objects.all()
    serializer_class = AdminLogSerializer
    permission_classes = [IsSuperUser]

class BackupViewSet(viewsets.ModelViewSet):
    queryset = Backup.objects.all()
    serializer_class = BackupSerializer
    permission_classes = [IsSuperUser]