from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = [
        ('worker', 'Worker'),
        ('owner', 'Owner'),
        ('admin', 'Admin'),
    ]

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True)
    farm_name = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='worker')
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email
