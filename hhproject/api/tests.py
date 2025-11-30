# api/tests.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from datetime import date
from .models import *
from .serializers import *

User = get_user_model()

class UserModelTest(TestCase):
    def test_create_user(self):
        """Тест создания обычного пользователя"""
        user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            phone='+79999999999',
            password='testpass123'
        )
        self.assertEqual(user.email, 'test@example.com')
        print("✅ test_create_user - ПРОЙДЕН")

    def test_create_superuser(self):
        """Тест создания суперпользователя"""
        admin_user = User.objects.create_superuser(
            email='admin@example.com',
            username='admin',
            phone='+78888888888',
            password='adminpass123'
        )
        self.assertTrue(admin_user.is_superuser)
        print("✅ test_create_superuser - ПРОЙДЕН")

class CompanyModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='company@example.com',
            username='companyuser',
            phone='+77777777777',
            password='testpass123',
            user_type='company'
        )
    
    def test_company_creation(self):
        """Тест создания компании"""
        company = Company.objects.create(
            user=self.user,
            name='Test Company',
            number='1234567890',
            industry='IT',
            description='Test description',
            status=Company.STATUS_PENDING
        )
        self.assertEqual(company.name, 'Test Company')
        print("✅ test_company_creation - ПРОЙДЕН")

class ApplicantModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='applicant@example.com',
            username='applicantuser',
            phone='+76666666666',
            password='testpass123',
            user_type='applicant'
        )
    
    def test_applicant_creation(self):
        """Тест создания соискателя"""
        applicant = Applicant.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            birth_date=date(1990, 1, 1),
            resume='Test resume content'
        )
        self.assertEqual(applicant.first_name, 'John')
        print("✅ test_applicant_creation - ПРОЙДЕН")

class VacancyModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='company@example.com',
            username='companyuser',
            phone='+75555555555',
            password='testpass123',
            user_type='company'
        )
        self.company = Company.objects.create(
            user=self.user,
            name='Test Company',
            number='1234567890',
            industry='IT',
            description='Test description'
        )
        self.work_condition = WorkConditions.objects.create(work_conditions_name='Офис')
        self.status = StatusVacancies.objects.create(status_vacancies_name='Активна')
    
    def test_vacancy_creation(self):
        """Тест создания вакансии"""
        vacancy = Vacancy.objects.create(
            company=self.company,
            work_conditions=self.work_condition,
            position='Python Developer',
            description='Test description',
            requirements='Test requirements',
            salary_min=50000,
            salary_max=100000,
            status=self.status,
            experience='1-3 года',
            city='Москва',
            category='IT'
        )
        self.assertEqual(vacancy.position, 'Python Developer')
        print("✅ test_vacancy_creation - ПРОЙДЕН")

# СЕРИАЛИЗАТОРЫ ТЕСТЫ
class UserSerializerTest(TestCase):
    def test_user_serializer(self):
        """Тест сериализатора пользователя"""
        user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            phone='+79999999999',
            password='testpass123'
        )
        serializer = UserSerializer(user)
        self.assertEqual(serializer.data['email'], 'test@example.com')
        print("✅ test_user_serializer - ПРОЙДЕН")

class CompanySerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='company@example.com',
            username='companyuser',
            phone='+77777777777',
            password='testpass123',
            user_type='company'
        )
    
    def test_company_serializer(self):
        """Тест сериализатора компании"""
        company = Company.objects.create(
            user=self.user,
            name='Test Company',
            number='1234567890',
            industry='IT',
            description='Test description'
        )
        serializer = CompanySerializer(company)
        self.assertEqual(serializer.data['name'], 'Test Company')
        print("✅ test_company_serializer - ПРОЙДЕН")

# API ТЕСТЫ
class BaseAPITestCase(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email='admin@example.com',
            username='admin',
            phone='+79999999999',
            password='adminpass123'
        )
        
        self.regular_user = User.objects.create_user(
            email='user@example.com',
            username='regularuser',
            phone='+78888888888',
            password='userpass123'
        )
        
        self.create_test_data()
        self.client = APIClient()
        self.client.force_authenticate(user=self.superuser)
    
    def create_test_data(self):
        """Создание тестовых данных"""
        self.company_user = User.objects.create_user(
            email='company@example.com',
            username='companyuser',
            phone='+77777777777',
            password='testpass123',
            user_type='company'
        )
        self.company = Company.objects.create(
            user=self.company_user,
            name='Test Company',
            number='1234567890',
            industry='IT',
            description='Test description'
        )
        
        self.applicant_user = User.objects.create_user(
            email='applicant@example.com',
            username='applicantuser',
            phone='+76666666666',
            password='testpass123',
            user_type='applicant'
        )
        self.applicant = Applicant.objects.create(
            user=self.applicant_user,
            first_name='John',
            last_name='Doe',
            birth_date=date(1990, 1, 1),
            resume='Test resume'
        )
        
        self.work_condition = WorkConditions.objects.create(work_conditions_name='Офис')
        self.vacancy_status = StatusVacancies.objects.create(status_vacancies_name='Активна')
        self.response_status = StatusResponse.objects.create(status_response_name='На рассмотрении')
        
        self.vacancy = Vacancy.objects.create(
            company=self.company,
            work_conditions=self.work_condition,
            position='Python Developer',
            description='Test description',
            requirements='Test requirements',
            salary_min=50000,
            salary_max=100000,
            status=self.vacancy_status,
            experience='1-3 года',
            city='Москва',
            category='IT'
        )

class CompanyViewSetTest(BaseAPITestCase):
    def test_list_companies_as_superuser(self):
        """Тест получения списка компаний суперпользователем"""
        url = reverse('company-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ test_list_companies_as_superuser - ПРОЙДЕН")
    
    
    
    def test_access_denied_for_regular_user(self):
        """Тест запрета доступа для обычного пользователя"""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse('company-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        print("✅ test_access_denied_for_regular_user - ПРОЙДЕН")

class VacancyViewSetTest(BaseAPITestCase):
    def test_list_vacancies(self):
        """Тест получения списка вакансий"""
        url = reverse('vacancy-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ test_list_vacancies - ПРОЙДЕН")
    
    def test_retrieve_vacancy(self):
        """Тест получения конкретной вакансии"""
        url = reverse('vacancy-detail', kwargs={'pk': self.vacancy.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ test_retrieve_vacancy - ПРОЙДЕН")
    
    def test_create_vacancy(self):
        """Тест создания вакансии"""
        url = reverse('vacancy-list')
        data = {
            'position': 'Django Developer',
            'description': 'New vacancy description',
            'requirements': 'Python, Django, DRF',
            'salary_min': 60000,
            'salary_max': 120000,
            'experience': '3-6 лет',
            'city': 'Санкт-Петербург',
            'category': 'IT',
            'company': self.company.pk,
            'work_conditions': self.work_condition.pk,
            'status': self.vacancy_status.pk
        }
        response = self.client.post(url, data)
        
        if response.status_code != status.HTTP_201_CREATED:
            print(f"❌ test_create_vacancy - ОШИБКА: {response.data}")
        else:
            print("✅ test_create_vacancy - ПРОЙДЕН")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

class ApplicantViewSetTest(BaseAPITestCase):
    def test_list_applicants(self):
        """Тест получения списка соискателей"""
        url = reverse('applicant-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ test_list_applicants - ПРОЙДЕН")
    
    def test_update_applicant(self):
        """Тест обновления соискателя"""
        url = reverse('applicant-detail', kwargs={'pk': self.applicant.pk})
        data = {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'birth_date': '1992-02-02',
            'resume': 'Updated resume'
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ test_update_applicant - ПРОЙДЕН")

class ComplaintViewSetTest(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.complaint = Complaint.objects.create(
            vacancy=self.vacancy,
            complainant=self.regular_user,
            complaint_type='spam',
            description='Test complaint description'
        )
    
    def test_list_complaints(self):
        """Тест получения списка жалоб"""
        url = reverse('complaint-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ test_list_complaints - ПРОЙДЕН")
    
    def test_update_complaint_status(self):
        """Тест обновления статуса жалобы"""
        url = reverse('complaint-detail', kwargs={'pk': self.complaint.pk})
        data = {'status': 'resolved', 'admin_notes': 'Complaint resolved'}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ test_update_complaint_status - ПРОЙДЕН")

class ResponseViewSetTest(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.response_obj = Response.objects.create(
            applicants=self.applicant,
            vacancy=self.vacancy,
            status=self.response_status
        )
    
    def test_list_responses(self):
        """Тест получения списка откликов"""
        url = reverse('response-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ test_list_responses - ПРОЙДЕН")
    
    def test_update_response_status(self):
        """Тест обновления статуса отклика"""
        new_status = StatusResponse.objects.create(status_response_name='Принято')
        url = reverse('response-detail', kwargs={'pk': self.response_obj.pk})
        data = {'status': new_status.pk}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ test_update_response_status - ПРОЙДЕН")

class PermissionTest(BaseAPITestCase):
    def test_unauthorized_access(self):
        """Тест доступа без авторизации"""
        self.client.force_authenticate(user=None)
        url = reverse('company-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        print("✅ test_unauthorized_access - ПРОЙДЕН")
    
    def test_regular_user_access(self):
        """Тест доступа обычного пользователя"""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse('vacancy-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        print("✅ test_regular_user_access - ПРОЙДЕН")

# Запуск с красивым выводом
def run_tests():
    print("🚀 ЗАПУСК ТЕСТОВ API")
    print("=" * 50)