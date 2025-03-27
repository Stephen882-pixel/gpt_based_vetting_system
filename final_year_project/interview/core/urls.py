from django.urls import path
from .views import register, user_login, user_logout, home, skill_create, interview_results,start_interview

urlpatterns = [
    path('register/', register, name='register'),
    path('login/', user_login, name='login'),
    path('logout/', user_logout, name='logout'),
    path('home/', home, name='home'),
    path('skills/create/', skill_create, name='skill_create'),
    path('interview/start/', start_interview, name='start_interview'),
    path('interview/results/', interview_results, name='interview_results'),
]