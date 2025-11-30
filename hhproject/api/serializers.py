from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from home.models import *

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ('email', 'username', 'phone', 'password', 'password2', 'user_type')
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Пароли не совпадают"})
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'phone', 'user_type', 'first_name', 'last_name')
        read_only_fields = ('id', 'user_type')

class CompanySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Company
        fields = '__all__'
        read_only_fields = ('created_at', 'status')

class CompanyStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ('id', 'status', 'admin_notes')
    
    def update(self, instance, validated_data):
        instance.status = validated_data.get('status', instance.status)
        instance.save()
        
        # Логируем действие
        AdminLog.objects.create(
            admin=self.context['request'].user,
            action='company_approved' if instance.status == Company.STATUS_APPROVED else 'company_rejected',
            target_company=instance,
            details=f"Статус изменен на {instance.get_status_display()}"
        )
        return instance

class ApplicantSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    full_name = serializers.CharField(source='__str__', read_only=True)
    
    class Meta:
        model = Applicant
        fields = '__all__'

class EmployeeSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    
    class Meta:
        model = Employee
        fields = '__all__'

class WorkConditionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkConditions
        fields = '__all__'

class StatusVacanciesSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusVacancies
        fields = '__all__'

class StatusResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusResponse
        fields = '__all__'

class VacancyListSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    work_conditions_name = serializers.CharField(source='work_conditions.work_conditions_name', read_only=True)
    status_name = serializers.CharField(source='status.status_vacancies_name', read_only=True)
    is_favorite = serializers.SerializerMethodField()
    
    class Meta:
        model = Vacancy
        fields = ('id', 'position', 'company_name', 'salary_min', 'salary_max', 
                 'city', 'category', 'experience', 'work_conditions_name',
                 'status_name', 'views', 'created_date', 'is_favorite')
    
    def get_is_favorite(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                applicant = request.user.applicant
                return obj.favorites_set.filter(applicant=applicant).exists()
            except Applicant.DoesNotExist:
                return False
        return False

class VacancyDetailSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    work_conditions_name = serializers.CharField(source='work_conditions.work_conditions_name', read_only=True)
    status_name = serializers.CharField(source='status.status_vacancies_name', read_only=True)
    has_applied = serializers.SerializerMethodField()
    is_favorite = serializers.SerializerMethodField()
    
    class Meta:
        model = Vacancy
        fields = '__all__'
    
    def get_has_applied(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                applicant = request.user.applicant
                return Response.objects.filter(applicants=applicant, vacancy=obj).exists()
            except Applicant.DoesNotExist:
                return False
        return False
    
    def get_is_favorite(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                applicant = request.user.applicant
                return Favorites.objects.filter(applicant=applicant, vacancy=obj).exists()
            except Applicant.DoesNotExist:
                return False
        return False

class ComplaintSerializer(serializers.ModelSerializer):
    complainant_email = serializers.CharField(source='complainant.email', read_only=True)
    vacancy_position = serializers.CharField(source='vacancy.position', read_only=True)
    company_name = serializers.CharField(source='vacancy.company.name', read_only=True)
    
    class Meta:
        model = Complaint
        fields = '__all__'
        read_only_fields = ('complainant', 'created_at', 'resolved_at', 'status')

class ResponseSerializer(serializers.ModelSerializer):
    applicant_name = serializers.CharField(source='applicants.__str__', read_only=True)
    vacancy_position = serializers.CharField(source='vacancy.position', read_only=True)
    company_name = serializers.CharField(source='vacancy.company.name', read_only=True)
    status_name = serializers.CharField(source='status.status_response_name', read_only=True)
    
    class Meta:
        model = Response
        fields = '__all__'
        read_only_fields = ('response_date',)

class FavoritesSerializer(serializers.ModelSerializer):
    vacancy_details = VacancyListSerializer(source='vacancy', read_only=True)
    
    class Meta:
        model = Favorites
        fields = ('id', 'vacancy', 'vacancy_details', 'added_date')
        read_only_fields = ('added_date',)

class AdminLogSerializer(serializers.ModelSerializer):
    admin_username = serializers.CharField(source='admin.username', read_only=True)
    company_name = serializers.CharField(source='target_company.name', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    
    class Meta:
        model = AdminLog
        fields = '__all__'

class BackupSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    file_size_display = serializers.CharField(source='get_file_size_display', read_only=True)
    
    class Meta:
        model = Backup
        fields = '__all__'
        read_only_fields = ('file_size', 'created_at')

