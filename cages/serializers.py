from rest_framework import serializers
from .models import Cage, Chicken, Egg, Notification

class CageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cage
        fields = ['id', 'name', 'capacity', 'current_count', 'created_at', 'updated_at']
        read_only_fields = ['current_count', 'created_at', 'updated_at']

class ChickenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chicken
        fields = ['id', 'cage', 'tag_id', 'gender', 'breed', 'age_weeks', 'weight_kg', 'health_status', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class EggSerializer(serializers.ModelSerializer):
    chicken_tag = serializers.CharField(source='chicken.tag_id', read_only=True)

    class Meta:
        model = Egg
        fields = ['id', 'chicken', 'chicken_tag', 'laid_date', 'weight_g', 'quality', 'created_at']
        read_only_fields = ['created_at']


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'notification_type', 'title', 'message', 'is_read', 'created_at', 'metadata']
        read_only_fields = ['id', 'notification_type', 'title', 'message', 'created_at', 'metadata']