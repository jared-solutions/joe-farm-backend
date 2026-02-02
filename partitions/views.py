from rest_framework import viewsets
from .models import Partition
from .serializers import PartitionSerializer

class PartitionViewSet(viewsets.ModelViewSet):
    serializer_class = PartitionSerializer

    def get_queryset(self):
        return Partition.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
