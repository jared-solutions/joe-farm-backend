from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('profile/update/', views.update_profile, name='update_profile'),
    path('password-reset/', views.password_reset, name='password_reset'),
    path('users/', views.users_list, name='users_list'),
    path('users/<int:user_id>/', views.delete_user, name='delete_user'),
    path('users/<int:user_id>/approve/', views.approve_user, name='approve_user'),
    path('pending-users/', views.pending_users, name='pending_users'),
]