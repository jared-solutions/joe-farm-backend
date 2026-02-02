from django.db import models
from authentication.models import User

class Partition(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    total_capacity = models.IntegerField()
    current_occupancy = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.user.farm_name}"

    @property
    def available_space(self):
        return self.total_capacity - self.current_occupancy
