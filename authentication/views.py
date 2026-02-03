from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import logout
from django.contrib.auth import get_user_model
from .serializers import RegisterSerializer, LoginSerializer, UserSerializer

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    # Check if there are any existing users
    User = get_user_model()
    user_count = User.objects.count()
    
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        
        # First user becomes owner and is auto-approved
        if user_count == 0:
            user.role = 'owner'
            user.is_approved = True
            user.save()
        else:
            user.is_approved = False
            user.save()
            
        # Only generate token for approved users
        if user.is_approved:
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'user': UserSerializer(user).data,
                'token': token.key,
                'message': 'Welcome, Owner!'
            }, status=status.HTTP_201_CREATED)
        else:
            # Delete token if it was created (shouldn't happen but just in case)
            Token.objects.filter(user=user).delete()
            return Response({
                'user': UserSerializer(user).data,
                'message': 'Registration successful! Waiting for owner approval.'
            }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    print("Login request data:", request.data)
    serializer = LoginSerializer(data=request.data)
    print("Serializer is_valid:", serializer.is_valid())
    if not serializer.is_valid():
        print("Serializer errors:", serializer.errors)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        
        # Check if user is approved
        if not user.is_approved:
            return Response({
                'error': 'Your account is pending approval. Please contact the farm owner.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'user': UserSerializer(user).data,
            'token': token.key
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def logout_view(request):
    request.user.auth_token.delete()
    logout(request)
    return Response({'message': 'Successfully logged out'})

@api_view(['GET'])
def profile(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data)

@api_view(['PUT'])
def update_profile(request):
    user = request.user
    data = request.data.copy()

    # Handle password change - require current password verification
    if 'password' in data and data['password']:
        current_password = data.get('current_password')
        if not current_password:
            return Response({
                'error': 'Current password is required to change password'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Verify current password
        if not user.check_password(current_password):
            return Response({
                'error': 'Current password is incorrect'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Set new password
        user.set_password(data['password'])

        # Remove password fields from data to avoid double processing
        data.pop('password', None)
        data.pop('current_password', None)

    serializer = UserSerializer(user, data=data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response({
            'user': serializer.data,
            'message': 'Profile updated successfully'
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset(request):
    email = request.data.get('email')
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        from django.contrib.auth import get_user_model
        from django.core.mail import send_mail
        from django.conf import settings
        import random
        import string

        User = get_user_model()
        user = User.objects.get(email=email)

        # Generate a 6-digit OTP
        otp = ''.join(random.choices(string.digits, k=6))

        # Store OTP in user model (you'd need to add an otp field to the User model)
        # For now, we'll store it temporarily in the session or cache
        from django.core.cache import cache
        cache.set(f'password_reset_otp_{email}', otp, 300)  # 5 minutes expiry

        # For development/testing, also print the OTP to console
        print(f"Password reset OTP for {email}: {otp}")

        # Send email with OTP
        subject = 'Password Reset OTP - EggVentory'
        message = f'''
        Hello {user.username},

        You have requested to reset your password for EggVentory.

        Your OTP (One-Time Password) is: {otp}

        This OTP will expire in 5 minutes.

        If you did not request this password reset, please ignore this email.

        Best regards,
        EggVentory Team
        '''
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [email]

        send_mail(subject, message, from_email, recipient_list, fail_silently=False)

        return Response({'message': 'Password reset OTP sent to your email'})
    except User.DoesNotExist:
        # Don't reveal if email exists or not for security
        return Response({'message': 'If an account with this email exists, a password reset OTP has been sent'})
    except Exception as e:
        return Response({'error': 'Failed to send password reset email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def users_list(request):
    """
    Get list of all users (for admin/owner management)
    """
    User = get_user_model()
    users = User.objects.all().order_by('-date_joined')
    serializer = UserSerializer(users, many=True)
    return Response(serializer.data)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_user(request, user_id):
    """
    Delete a user (for admin/owner management)
    """
    try:
        User = get_user_model()
        user = User.objects.get(id=user_id)

        # Prevent deleting yourself
        if user.id == request.user.id:
            return Response({'error': 'Cannot delete your own account'}, status=status.HTTP_400_BAD_REQUEST)

        user.delete()
        return Response({'message': 'User deleted successfully'})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_user(request, user_id):
    """
    Approve a pending user (owner only)
    """
    try:
        # Only owners can approve users
        if request.user.role != 'owner':
            return Response({'error': 'Only owners can approve users'}, status=status.HTTP_403_FORBIDDEN)
        
        User = get_user_model()
        user = User.objects.get(id=user_id)
        
        user.is_approved = True
        user.save()
        
        return Response({
            'message': f'User {user.username} has been approved successfully',
            'user': UserSerializer(user).data
        })
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pending_users(request):
    """
    Get list of pending users waiting for approval
    """
    try:
        # Only owners can view pending users
        if request.user.role != 'owner':
            return Response({'error': 'Only owners can view pending users'}, status=status.HTTP_403_FORBIDDEN)
        
        User = get_user_model()
        pending_users = User.objects.filter(is_approved=False).order_by('-created_at')
        serializer = UserSerializer(pending_users, many=True)
        return Response(serializer.data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
