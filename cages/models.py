from django.db import models
from authentication.models import User

class Cage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    capacity = models.IntegerField()
    current_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.user.farm_name}"

class Chicken(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]

    cage = models.ForeignKey(Cage, on_delete=models.CASCADE)
    tag_id = models.CharField(max_length=50, unique=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    breed = models.CharField(max_length=100)
    age_weeks = models.IntegerField()
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2)
    health_status = models.CharField(max_length=100, default='Healthy')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Chicken {self.tag_id}"

class Egg(models.Model):
    chicken = models.ForeignKey(Chicken, on_delete=models.CASCADE, null=True, blank=True)
    laid_date = models.DateField()
    weight_g = models.DecimalField(max_digits=5, decimal_places=2)
    quality = models.CharField(max_length=50)
    source = models.CharField(max_length=50, default='cage')  # 'cage' or 'shade'
    cage_id = models.IntegerField(null=True, blank=True)  # Store cage ID for performance tracking
    partition_index = models.IntegerField(null=True, blank=True)  # Store partition info (0=front, 1=back)
    box_number = models.IntegerField(null=True, blank=True)  # Store box number (1-4 or 1-8 depending on cage type)
    recorded_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(blank=True, default=dict)  # Store additional data like egg count

    def __str__(self):
        if self.chicken:
            return f"Egg from {self.chicken.tag_id} on {self.laid_date}"
        else:
            return f"{self.source.title()} egg on {self.laid_date}"

class Store(models.Model):
    """Egg stock management in trays"""
    trays_in_stock = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Store'
        verbose_name_plural = 'Store'

    def __str__(self):
        return f"Store: {self.trays_in_stock} trays"

class FeedPurchase(models.Model):
    """Weekly feed purchases"""
    date = models.DateField()
    feed_type = models.CharField(max_length=100, blank=True)
    quantity_kg = models.DecimalField(max_digits=8, decimal_places=2)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    cost_per_kg = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.quantity_kg and self.total_cost:
            self.cost_per_kg = self.total_cost / self.quantity_kg
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Feed Purchase: {self.quantity_kg}kg on {self.date}"

class FeedConsumption(models.Model):
    """Daily feed consumption"""
    date = models.DateField()
    quantity_used_kg = models.DecimalField(max_digits=8, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feed Used: {self.quantity_used_kg}kg on {self.date}"

class Sale(models.Model):
    """Egg sales"""
    date = models.DateField()
    trays_sold = models.IntegerField()
    price_per_tray = models.DecimalField(max_digits=8, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.total_amount = self.trays_sold * self.price_per_tray
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Sale: {self.trays_sold} trays on {self.date}"

class Expense(models.Model):
    EXPENSE_TYPES = [
        ('feed', 'Feed Cost'),
        ('medicine', 'Medicine/Vaccination'),
        ('transport', 'Transport'),
        ('maintenance', 'Maintenance/Other'),
    ]

    date = models.DateField()
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPES)
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    recorded_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.expense_type.title()}: {self.amount} on {self.date}"

class MedicalRecord(models.Model):
    """Medical records for chickens"""
    TREATMENT_TYPES = [
        ('vaccination', 'Vaccination'),
        ('medicine', 'Medicine'),
        ('checkup', 'Health Checkup'),
        ('treatment', 'Treatment'),
    ]

    chicken = models.ForeignKey(Chicken, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    treatment_type = models.CharField(max_length=20, choices=TREATMENT_TYPES)
    description = models.CharField(max_length=200)
    medication = models.CharField(max_length=100, blank=True)
    dosage = models.CharField(max_length=50, blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vet_name = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        chicken_info = f"Chicken {self.chicken.tag_id}" if self.chicken else "General"
        return f"{chicken_info}: {self.treatment_type.title()} on {self.date}"

class FarmSettings(models.Model):
    """Store farm-wide settings like total chicken count"""
    key = models.CharField(max_length=50, unique=True)
    value = models.CharField(max_length=100)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.key}: {self.value}"


class Notification(models.Model):
    """Notifications for farm owners"""
    NOTIFICATION_TYPES = [
        ('egg_collection', 'Egg Collection'),
        ('expense', 'Expense Recorded'),
        ('system', 'System Notification'),
    ]
    
    user = models.ForeignKey('authentication.User', on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)  # Store additional data like date, counts, etc.

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.user.username}"
