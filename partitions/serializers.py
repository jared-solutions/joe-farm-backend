from rest_framework import serializers
from .models import Partition

class PartitionSerializer(serializers.ModelSerializer):
    available_space = serializers.ReadOnlyField()

    class Meta:
        model = Partition
        fields = ['id', 'name', 'description', 'total_capacity', 'current_occupancy', 'available_space', 'created_at', 'updated_at']
        read_only_fields = ['available_space', 'created_at', 'updated_at']