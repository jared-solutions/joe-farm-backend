from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User

class UserSerializer(serializers.ModelSerializer):
    date_joined = serializers.DateTimeField(read_only=True)
    is_approved = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'phone', 'farm_name', 'first_name', 'last_name', 'role', 'is_approved', 'date_joined', 'created_at']

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'phone', 'farm_name', 'first_name', 'last_name', 'role']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            phone=validated_data.get('phone', ''),
            farm_name=validated_data.get('farm_name', ''),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            role=validated_data.get('role', 'worker')
        )
        return user

class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if email and password:
            user = authenticate(email=email, password=password)
            if not user:
                raise serializers.ValidationError('Invalid credentials')
        else:
            raise serializers.ValidationError('Must include email and password')

        data['user'] = user
        return data