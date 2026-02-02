
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count, Avg, Q
from datetime import datetime, timedelta
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from io import BytesIO
from .models import Cage, Chicken, Egg, Store, FeedPurchase, FeedConsumption, Sale, Expense, FarmSettings, MedicalRecord
from .serializers import CageSerializer, ChickenSerializer, EggSerializer

class CageViewSet(viewsets.ModelViewSet):
    serializer_class = CageSerializer

    def get_queryset(self):
        return Cage.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class ChickenViewSet(viewsets.ModelViewSet):
    serializer_class = ChickenSerializer

    def get_queryset(self):
        return Chicken.objects.filter(cage__user=self.request.user)

    def perform_create(self, serializer):
        cage = get_object_or_404(Cage, id=self.request.data.get('cage'), user=self.request.user)
        serializer.save()

        # Update cage current count
        cage.current_count = Chicken.objects.filter(cage=cage).count()
        cage.save()

class EggViewSet(viewsets.ModelViewSet):
    serializer_class = EggSerializer

    def get_queryset(self):
        return Egg.objects.filter(chicken__cage__user=self.request.user)

    def perform_create(self, serializer):
        chicken = get_object_or_404(Chicken, id=self.request.data.get('chicken'), cage__user=self.request.user)
        serializer.save()

    @action(detail=False, methods=['post'], url_path='submit-cage')
    def submit_cage(self, request):
        data = request.data
        cage_id = data.get('cageId')
        partitions = data.get('partitions', [])

        # Get the cage
        cage = get_object_or_404(Cage, id=cage_id, user=request.user)

        # Process each partition
        for partition in partitions:
            partition_index = partition.get('partitionIndex')
            eggs_collected = partition.get('eggsCollected', [])
            comments = partition.get('comments', '')

            # For each egg collected, create an egg record
            for egg_data in eggs_collected:
                # Create egg record for each collected egg
                # We'll associate it with a chicken from this cage if possible
                chicken = Chicken.objects.filter(cage=cage).first()
                Egg.objects.create(
                    chicken=chicken,  # Associate with first chicken in cage
                    laid_date=request.data.get('date', None),
                    weight_g=0.0,  # Default weight, can be updated later
                    quality='Good'  # Default quality rating
                )

        return Response({'message': 'Cage data submitted successfully'}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='submit-daily-collection')
    def submit_daily_collection(self, request):
        data = request.data
        print(f"DEBUG: submit_daily_collection called with data: {data}")
        collection_date = data.get('date')
        shade_eggs = data.get('shade_eggs', 0)
        cages_data = data.get('cages', [])

        # Validation
        if not collection_date:
            return Response({'detail': 'Date is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if data has already been submitted for this date by this user
        existing_eggs = Egg.objects.filter(
            laid_date=collection_date,
            recorded_by=request.user
        )

        if existing_eggs.exists():
            recorder_name = request.user.username or request.user.email
            return Response({
                'detail': f'Egg collection data has already been recorded for {collection_date} by {recorder_name}. Each date can only be recorded once per user.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Allow submission with just shade eggs or just cage data
        if shade_eggs <= 0 and not cages_data:
            return Response({'detail': 'Cannot submit empty data. Please enter egg counts or shade eggs.'}, status=status.HTTP_400_BAD_REQUEST)
        
        print(f"DEBUG: Data validation passed")
        
        try:
            # Process the daily egg collection data
            # We'll track eggs from both shade areas and cage collections

            total_eggs_collected = shade_eggs

            # Process shade eggs
            for i in range(shade_eggs):
                Egg.objects.create(
                    chicken=None,  # Shade eggs aren't tied to specific chickens
                    laid_date=collection_date,
                    weight_g=0.0,  # Weight measured separately if needed
                    quality='Good',  # Assumed good quality for shade eggs
                    source='shade'
                )

            # Process each cage
            for cage_data in cages_data:
                cage_id = cage_data.get('cageId')
                cage_type = cage_data.get('cageType')
                partitions = cage_data.get('partitions', [])

                if not cage_id:
                    continue

                # Assume cage_id is valid for this user

                # Process each partition
                for partition in partitions:
                    partition_index = partition.get('partitionIndex')
                    eggs_collected = partition.get('eggsCollected', [])
                    comments = partition.get('comments', '')
                    total_eggs_collected += len(eggs_collected)

                    # For each egg collected, create an egg record with detailed tracking
                    for egg_data in eggs_collected:
                        # Extract box number and count from egg data
                        box_number = None
                        egg_count = 1

                        if isinstance(egg_data, dict):
                            if 'boxNumber' in egg_data:
                                box_number = egg_data['boxNumber']
                            elif 'box_number' in egg_data:
                                box_number = egg_data['box_number']

                            if 'value' in egg_data:
                                egg_count = egg_data['value']
                            elif 'count' in egg_data:
                                egg_count = egg_data['count']

                        # Create individual egg records for each count in this box
                        for _ in range(egg_count):
                            Egg.objects.create(
                                chicken=None,  # Eggs collected from cages, not tied to specific chickens
                                laid_date=collection_date,
                                weight_g=0.0,  # Weight measured separately if needed
                                quality='Good',  # Quality assessment done during collection
                                source='cage',
                                cage_id=cage_id,
                                partition_index=partition_index - 1,  # Convert to 0-based indexing for storage
                                box_number=box_number,
                                recorded_by=request.user
                            )

            # Convert eggs to trays for storage (30 eggs per tray)
            trays_to_add = total_eggs_collected // 30
            if trays_to_add > 0:
                store, created = Store.objects.get_or_create(id=1, defaults={'trays_in_stock': 0})
                store.trays_in_stock += trays_to_add
                store.save()
            
            print(f"DEBUG: Submission successful, trays added: {trays_to_add}")
            
            return Response({'message': f'Daily collection submitted successfully. Added {trays_to_add} trays to store.'}, status=status.HTTP_201_CREATED)

        except Exception as e:
        
            print(f"DEBUG: Exception during submission: {str(e)}")
        
            return Response({'detail': f'Error processing submission: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_overview(request):
    """Dashboard overview for owners and admins - shows farm-wide statistics"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    # Get real data from database
    total_cages = Cage.objects.filter(user=request.user).count()

    # Get the total chicken count from settings or database
    chicken_setting = FarmSettings.objects.filter(key='total_chickens').first()
    if chicken_setting:
        try:
            total_chickens = int(chicken_setting.value)
        except (ValueError, TypeError):
            total_chickens = Chicken.objects.filter(cage__user=request.user).count()
    else:
        total_chickens = Chicken.objects.filter(cage__user=request.user).count()

    # Calculate egg production metrics with detailed breakdown
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # Get today's egg collection data
    today_eggs = Egg.objects.filter(laid_date=today).filter(
        Q(chicken__cage__user=request.user) | Q(recorded_by=request.user)
    )

    # Count eggs by source
    cage_eggs_today = today_eggs.filter(source='cage').count()
    shade_eggs_today = today_eggs.filter(source='shade').count()
    total_eggs_today = cage_eggs_today + shade_eggs_today

    # Break down eggs by cage for detailed reporting
    cage_breakdown = {}
    for cage_id in [1, 2]:  # Standard farm has 2 cages
        cage_eggs = today_eggs.filter(cage_id=cage_id, source='cage')

        # Count eggs in each partition
        front_eggs = cage_eggs.filter(partition_index=0).count()  # Front partition
        back_eggs = cage_eggs.filter(partition_index=1).count()   # Back partition

        if front_eggs > 0 or back_eggs > 0:
            cage_breakdown[cage_id] = {
                'total': front_eggs + back_eggs,
                'front': front_eggs,
                'back': back_eggs
            }

    # Weekly and monthly totals
    total_eggs_week = Egg.objects.filter(laid_date__gte=week_start, laid_date__lte=today).filter(
        Q(chicken__cage__user=request.user) | Q(recorded_by=request.user)
    ).count()
    total_eggs_month = Egg.objects.filter(laid_date__gte=month_start, laid_date__lte=today).filter(
        Q(chicken__cage__user=request.user) | Q(recorded_by=request.user)
    ).count()

    # Calculate averages
    days_this_month = (today - month_start).days + 1
    avg_daily_eggs = total_eggs_month / days_this_month if days_this_month > 0 else 0
    avg_weekly_eggs = total_eggs_week / 7
    avg_monthly_eggs = total_eggs_month

    # Calculate the laying percentage for the flock
    if total_chickens > 0:
        laying_percentage = total_eggs_today / total_chickens * 100
    else:
        laying_percentage = 0

    # Get feed requirements from farm settings, with a reasonable default
    feed_setting = FarmSettings.objects.filter(key='feed_per_chicken_daily_kg').first()
    if feed_setting:
        feed_per_chicken_daily = float(feed_setting.value)
    else:
        feed_per_chicken_daily = 0.12  # Standard feed requirement per chicken

    feed_requirement_daily = total_chickens * feed_per_chicken_daily
    feed_requirement_weekly = feed_requirement_daily * 7
    feed_requirement_monthly = feed_requirement_daily * 30

    # Estimate revenue based on current market prices
    revenue_daily = total_eggs_today * 0.15  # $0.15 per egg market rate
    revenue_weekly = total_eggs_week * 0.15
    revenue_monthly = total_eggs_month * 0.15

    # Get cage utilization
    total_capacity = Cage.objects.aggregate(total=Sum('capacity'))['total'] or 0
    current_occupancy = Chicken.objects.count()
    utilization_rate = (current_occupancy / total_capacity * 100) if total_capacity > 0 else 0

    # Convert eggs to trays for packaging (30 eggs = 1 tray)
    trays_today = total_eggs_today // 30
    remaining_eggs_today = total_eggs_today % 30
    trays_week = total_eggs_week // 30
    remaining_eggs_week = total_eggs_week % 30
    trays_month = total_eggs_month // 30
    remaining_eggs_month = total_eggs_month % 30

    # Calculate today's operating expenses
    today = datetime.now().date()

    # Get today's operating expenses (excluding feed purchases which are capital expenses)
    today_expenses = Expense.objects.filter(
        date=today
    ).exclude(expense_type='feed').aggregate(total=Sum('amount'))['total'] or 0

    # Calculate today's feed consumption cost based on actual usage
    # This represents the operating expense for feed consumed
    feed_cost_today = 0
    if total_chickens > 0 and feed_per_chicken_daily > 0:
        # Calculate expected daily feed consumption
        daily_feed_kg = total_chickens * feed_per_chicken_daily

        # Get cost per kg from recent feed purchases
        recent_purchases = FeedPurchase.objects.filter(
            date__gte=today - timedelta(days=90)  # Last 3 months for accurate average
        ).order_by('-date')

        if recent_purchases.exists():
            # Calculate weighted average cost per kg
            total_cost = 0
            total_qty = 0
            for purchase in recent_purchases:
                if purchase.quantity_kg and purchase.total_cost:
                    total_cost += purchase.total_cost
                    total_qty += purchase.quantity_kg

            if total_qty > 0:
                avg_cost_per_kg = total_cost / total_qty
                feed_cost_today = daily_feed_kg * avg_cost_per_kg
        else:
            # Use standard market rate if no purchase history available
            avg_cost_per_kg = 55.71  # Ksh per kg - current market rate
            feed_cost_today = daily_feed_kg * avg_cost_per_kg

    # Note: Feed purchases are capital expenses (inventory investment) and are not
    # included in daily operating expenses. Only feed consumption affects daily profit/loss.

    total_expenses_today = today_expenses + feed_cost_today

    # Get financial summary data for the dashboard
    from django.test import RequestFactory
    factory = RequestFactory()
    financial_request = factory.get('/api/cages/financial/summary/')
    financial_request.user = request.user
    financial_data = financial_summary(financial_request).data

    data = {
        'total_cages': total_cages,
        'total_chickens': total_chickens,
        'total_capacity': total_capacity,
        'utilization_rate': round(utilization_rate, 2),
        'egg_production': {
            'today': total_eggs_today,
            'today_breakdown': {
                'cage_eggs': cage_eggs_today,
                'shade_eggs': shade_eggs_today,
                'cages': cage_breakdown,
                'total': total_eggs_today
            },
            'this_week': total_eggs_week,
            'this_month': total_eggs_month,
            'avg_daily': round(avg_daily_eggs, 2),
            'avg_weekly': round(avg_weekly_eggs, 2),
            'avg_monthly': round(avg_monthly_eggs, 2),
            'laying_percentage': round(laying_percentage, 2),
        },
        'tray_calculations': {
            'today': {
                'trays': trays_today,
                'remaining_eggs': remaining_eggs_today
            },
            'this_week': {
                'trays': trays_week,
                'remaining_eggs': remaining_eggs_week
            },
            'this_month': {
                'trays': trays_month,
                'remaining_eggs': remaining_eggs_month
            }
        },
        'feed_requirements': {
            'daily_kg': round(feed_requirement_daily, 2),
            'weekly_kg': round(feed_requirement_weekly, 2),
            'monthly_kg': round(feed_requirement_monthly, 2),
        },
        'revenue_estimates': {
            'daily_usd': round(revenue_daily, 2),
            'weekly_usd': round(revenue_weekly, 2),
            'monthly_usd': round(revenue_monthly, 2),
        },
        # Include financial summary data from the financial API
        'total_hens': financial_data.get('total_hens', total_chickens),
        'eggs_today': financial_data.get('eggs_today', total_eggs_today),
        'trays_in_store': financial_data.get('trays_in_store', 0),
        'trays_sold': financial_data.get('trays_sold', 0),
        'total_revenue': financial_data.get('total_revenue', 0),
        'total_expenses': financial_data.get('total_expenses', 0),
        'expenses_today': round(total_expenses_today, 2),
        'profit_loss': financial_data.get('profit_loss', 0),
        'profit_margin': financial_data.get('profit_margin', 0),
        'feed_efficiency': financial_data.get('feed_efficiency', 0),
        'avg_eggs_per_hen': financial_data.get('avg_eggs_per_hen', 0),
        'feed_bought_week': financial_data.get('feed_bought_week', 0),
        'feed_remaining': financial_data.get('feed_remaining', 0)
    }

    return Response(data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def egg_collection_table(request):
    """Generate egg collection table data for PDF/Excel export"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    # Get date from query params, default to today
    collection_date = request.GET.get('date', datetime.now().date())

    if isinstance(collection_date, str):
        try:
            collection_date = datetime.strptime(collection_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    # Get actual egg data from database for the specified date
    eggs = Egg.objects.filter(
        laid_date=collection_date
    ).filter(
        # Include eggs from user's chickens or eggs recorded by this user
        Q(chicken__cage__user=request.user) | Q(recorded_by=request.user)
    )

    # Calculate laying percentage and performance comments
    chicken_setting = FarmSettings.objects.filter(key='total_chickens').first()
    total_chickens = int(chicken_setting.value) if chicken_setting else Chicken.objects.filter(cage__user=request.user).count()

    total_eggs_today = eggs.count()
    laying_percentage = (total_eggs_today / total_chickens * 100) if total_chickens > 0 else 0

    # Generate automatic performance comments based on laying percentage
    if laying_percentage >= 90:
        performance_comment = "Excellent laying performance! Flock is performing exceptionally well."
    elif laying_percentage >= 80:
        performance_comment = "Very good production. Flock health and feed quality are optimal."
    elif laying_percentage >= 70:
        performance_comment = "Good laying percentage. Monitor feed quality and health."
    elif laying_percentage >= 60:
        performance_comment = "Average production. Consider reviewing feed and health management."
    elif laying_percentage >= 50:
        performance_comment = "Below average production. Check for health issues or feed problems."
    elif laying_percentage >= 30:
        performance_comment = "Poor laying performance. Immediate attention to flock health required."
    else:
        performance_comment = "Critical: Very low production. Urgent veterinary attention needed."

    # Calculate laying percentage and performance comments
    chicken_setting = FarmSettings.objects.filter(key='total_chickens').first()
    total_chickens = int(chicken_setting.value) if chicken_setting else Chicken.objects.filter(cage__user=request.user).count()

    total_eggs_today = eggs.count()
    laying_percentage = (total_eggs_today / total_chickens * 100) if total_chickens > 0 else 0

    # Generate automatic performance comments based on laying percentage
    if laying_percentage >= 90:
        performance_comment = "Excellent laying performance! Flock is performing exceptionally well."
    elif laying_percentage >= 80:
        performance_comment = "Very good production. Flock health and feed quality are optimal."
    elif laying_percentage >= 70:
        performance_comment = "Good laying percentage. Monitor feed quality and health."
    elif laying_percentage >= 60:
        performance_comment = "Average production. Consider reviewing feed and health management."
    elif laying_percentage >= 50:
        performance_comment = "Below average production. Check for health issues or feed problems."
    elif laying_percentage >= 30:
        performance_comment = "Poor laying performance. Immediate attention to flock health required."
    else:
        performance_comment = "Critical: Very low production. Urgent veterinary attention needed."

    # Organize eggs by cage, partition, and box for the collection table
    cage_data = {}
    shade_eggs = 0

    for egg in eggs:
        if egg.source == 'shade':
            shade_eggs += 1
        elif egg.cage_id is not None and egg.box_number is not None:
            cage_id = egg.cage_id
            partition = egg.partition_index or 0
            box = egg.box_number

            if cage_id not in cage_data:
                cage_data[cage_id] = {}

            if partition not in cage_data[cage_id]:
                cage_data[cage_id][partition] = {}

            if box not in cage_data[cage_id][partition]:
                cage_data[cage_id][partition][box] = 0

            cage_data[cage_id][partition][box] += 1

    # Format data for table display - exact frontend structure
    table_data = {
        'date': collection_date.isoformat(),
        'cages': [],
        'shade_total': shade_eggs,
        'grand_total': len(eggs),
        'laying_percentage': round(laying_percentage, 2),
        'performance_comment': performance_comment
    }

    # Convert cage data to match frontend structure exactly
    # Get actual cages from database
    user_cages = Cage.objects.filter(user=request.user).values_list('id', flat=True)
    if not user_cages:
        # If no cages exist, use default cages 1 and 2 for display purposes
        user_cages = [1, 2]

    for cage_id in user_cages:
        cage_info = {
            'cage_id': cage_id,
            'front_partition': [],
            'back_partition': []
        }

        # Frontend structure: each cage has front and back partitions
        # Each partition has 4 rows x 4 columns = 16 boxes total
        # Data is stored with partition_index (0=front, 1=back)

        # Front partition (partition_index 0)
        front_data = cage_data.get(cage_id, {}).get(0, {})  # partition_index 0
        for box_num in range(1, 17):  # 16 boxes (4x4 grid)
            count = front_data.get(box_num, 0) if isinstance(front_data, dict) else 0
            cage_info['front_partition'].append({
                'box': box_num,
                'eggs': count
            })

        # Back partition (partition_index 1)
        back_data = cage_data.get(cage_id, {}).get(1, {})  # partition_index 1
        for box_num in range(1, 17):  # 16 boxes (4x4 grid)
            count = back_data.get(box_num, 0) if isinstance(back_data, dict) else 0
            cage_info['back_partition'].append({
                'box': box_num,
                'eggs': count
            })

        cage_info['cage_total'] = sum(p['eggs'] for p in cage_info['front_partition']) + sum(p['eggs'] for p in cage_info['back_partition'])
        table_data['cages'].append(cage_info)

    table_data['cage_total'] = sum(c['cage_total'] for c in table_data['cages'])

    return Response(table_data)

@api_view(['GET', 'PUT', 'POST'])
@permission_classes([IsAuthenticated])
def chicken_count(request):
    """Get and update total chicken count and farm settings"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        # Check if a specific key is requested
        key = request.GET.get('key')
        if key:
            # Return specific setting
            setting = FarmSettings.objects.filter(key=key).first()
            if setting:
                return Response({'key': key, 'value': setting.value})
            else:
                return Response({'key': key, 'value': None, 'detail': f'Setting {key} not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Return total chicken count (default behavior)
        setting = FarmSettings.objects.filter(key='total_chickens').first()
        if setting:
            total_chickens = int(setting.value)
        else:
            total_chickens = Chicken.objects.count()
        return Response({'total_chickens': total_chickens})

    elif request.method == 'PUT':
        new_count = request.data.get('total_chickens')
        if new_count is None or not isinstance(new_count, int) or new_count < 0:
            return Response({'detail': 'Valid total_chickens count required'}, status=status.HTTP_400_BAD_REQUEST)

        # Store the count in FarmSettings
        setting, created = FarmSettings.objects.get_or_create(
            key='total_chickens',
            defaults={'value': str(new_count)}
        )
        if not created:
            setting.value = str(new_count)
            setting.save()

        return Response({'message': f'Chicken count updated to {new_count}', 'total_chickens': new_count})

    elif request.method == 'POST':
        # Handle farm settings updates
        key = request.data.get('key')
        value = request.data.get('value')

        if not key or value is None:
            return Response({'detail': 'key and value are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Store the setting
        setting, created = FarmSettings.objects.get_or_create(
            key=key,
            defaults={'value': str(value)}
        )
        if not created:
            setting.value = str(value)
            setting.save()

        return Response({'message': f'Setting {key} updated to {value}'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def store_status(request):
    """Get current store status"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    store, created = Store.objects.get_or_create(id=1, defaults={'trays_in_stock': 0})
    return Response({'trays_in_stock': store.trays_in_stock})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_sale(request):
    """Record egg sales"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    data = request.data
    trays_sold = data.get('trays_sold')
    price_per_tray = data.get('price_per_tray')
    date = data.get('date', datetime.now().date())

    if not trays_sold or not price_per_tray:
        return Response({'detail': 'trays_sold and price_per_tray are required'}, status=status.HTTP_400_BAD_REQUEST)

    # Record the sale
    Sale.objects.create(
        date=date,
        trays_sold=trays_sold,
        price_per_tray=price_per_tray
    )

    # Update store stock
    store, created = Store.objects.get_or_create(id=1, defaults={'trays_in_stock': 0})
    if store.trays_in_stock >= trays_sold:
        store.trays_in_stock -= trays_sold
        store.save()
        return Response({'message': f'Sale recorded. {trays_sold} trays sold. Store now has {store.trays_in_stock} trays.'})
    else:
        return Response({'detail': f'Insufficient stock. Only {store.trays_in_stock} trays available.'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_feed_purchase(request):
    """Record feed purchase"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    data = request.data
    quantity_kg = data.get('quantity_kg')
    total_cost = data.get('total_cost')
    feed_type = data.get('feed_type', '')
    date = data.get('date', datetime.now().date())

    if not quantity_kg or not total_cost:
        return Response({'detail': 'quantity_kg and total_cost are required'}, status=status.HTTP_400_BAD_REQUEST)

    FeedPurchase.objects.create(
        date=date,
        feed_type=feed_type,
        quantity_kg=quantity_kg,
        total_cost=total_cost
    )

    return Response({'message': f'Feed purchase recorded: {quantity_kg}kg for ${total_cost}'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_feed_consumption(request):
    """Record daily feed consumption"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    data = request.data
    quantity_used_kg = data.get('quantity_used_kg')
    date = data.get('date', datetime.now().date())

    if not quantity_used_kg:
        return Response({'detail': 'quantity_used_kg is required'}, status=status.HTTP_400_BAD_REQUEST)

    FeedConsumption.objects.create(
        date=date,
        quantity_used_kg=quantity_used_kg
    )

    return Response({'message': f'Feed consumption recorded: {quantity_used_kg}kg used on {date}'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_expense(request):
    """Record expenses"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    data = request.data
    expense_type = data.get('expense_type')
    amount = data.get('amount')
    description = data.get('description', '')
    date = data.get('date', datetime.now().date())

    if not expense_type or not amount:
        return Response({'detail': 'expense_type and amount are required'}, status=status.HTTP_400_BAD_REQUEST)

    Expense.objects.create(
        date=date,
        expense_type=expense_type,
        description=description,
        amount=amount
    )

    return Response({'message': f'Expense recorded: {expense_type} - ${amount}'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def financial_summary(request):
    """Get financial summary for current week with proper expense accounting"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    # Get current week dates
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Get chicken count from FarmSettings
    chicken_setting = FarmSettings.objects.filter(key='total_chickens').first()
    if chicken_setting:
        try:
            total_chickens = int(chicken_setting.value)
        except (ValueError, TypeError):
            total_chickens = 0
    else:
        total_chickens = 0

    # Get feed consumption rate
    feed_setting = FarmSettings.objects.filter(key='feed_per_chicken_daily_kg').first()
    if feed_setting:
        try:
            feed_per_chicken_daily = float(feed_setting.value)
        except (ValueError, TypeError):
            feed_per_chicken_daily = 0.12
    else:
        feed_per_chicken_daily = 0.12

    # Calculate revenue from sales (all sales for the week)
    weekly_sales = Sale.objects.filter(date__gte=week_start, date__lte=week_end)
    total_revenue = weekly_sales.aggregate(total=Sum('total_amount'))['total'] or 0

    # Calculate OPERATING EXPENSES (costs of running the farm)
    # 1. Feed consumption costs (actual daily feed usage)
    weekly_feed_consumption = FeedConsumption.objects.filter(date__gte=week_start, date__lte=week_end)
    total_feed_used_kg = weekly_feed_consumption.aggregate(total=Sum('quantity_used_kg'))['total'] or 0

    # Calculate feed cost based on consumption (using weighted average price)
    feed_cost_this_week = 0
    if total_feed_used_kg > 0:
        # Get feed purchases to calculate weighted average cost
        feed_purchases = FeedPurchase.objects.filter(date__gte=week_start - timedelta(days=90), date__lte=week_end)
        if feed_purchases.exists():
            total_cost = 0
            total_qty = 0
            for purchase in feed_purchases:
                if purchase.quantity_kg and purchase.total_cost:
                    total_cost += purchase.total_cost
                    total_qty += purchase.quantity_kg

            if total_qty > 0:
                avg_cost_per_kg = total_cost / total_qty
                feed_cost_this_week = total_feed_used_kg * avg_cost_per_kg

    # 2. Other operating expenses (medicine, labor, utilities, etc.) - exclude feed purchases
    weekly_expenses = Expense.objects.filter(
        date__gte=week_start,
        date__lte=week_end
    ).exclude(expense_type='feed')  # Feed purchases are capital expenses
    total_operating_expenses = weekly_expenses.aggregate(total=Sum('amount'))['total'] or 0

    # Total operating costs = feed consumption + other expenses
    total_operating_costs = feed_cost_this_week + total_operating_expenses

    # Calculate CAPITAL EXPENSES (investments) - feed purchases
    weekly_feed_purchases = FeedPurchase.objects.filter(date__gte=week_start, date__lte=week_end)
    total_capital_expenses = weekly_feed_purchases.aggregate(total=Sum('total_cost'))['total'] or 0

    # Calculate profit/loss (revenue - operating costs)
    profit_loss = total_revenue - total_operating_costs
    profit_margin = (profit_loss / total_revenue * 100) if total_revenue > 0 else 0

    # Get current metrics from database
    eggs_today = Egg.objects.filter(laid_date=today, chicken__cage__user=request.user).count()
    store, created = Store.objects.get_or_create(id=1, defaults={'trays_in_stock': 0})

    # Calculate feed efficiency (eggs per kg of feed)
    weekly_eggs = Egg.objects.filter(laid_date__gte=week_start, laid_date__lte=week_end).count()
    feed_efficiency = weekly_eggs / total_feed_used_kg if total_feed_used_kg > 0 else 0

    # Calculate avg eggs per hen
    avg_eggs_per_hen = eggs_today / total_chickens if total_chickens > 0 else 0

    # Calculate feed inventory (bought - used)
    total_feed_bought = FeedPurchase.objects.aggregate(total=Sum('quantity_kg'))['total'] or 0
    total_feed_used = FeedConsumption.objects.aggregate(total=Sum('quantity_used_kg'))['total'] or 0
    feed_remaining = total_feed_bought - total_feed_used

    # Calculate feed bought this week
    feed_bought_week = weekly_feed_purchases.aggregate(total=Sum('quantity_kg'))['total'] or 0

    data = {
        'total_hens': total_chickens,
        'eggs_today': eggs_today,
        'trays_in_store': store.trays_in_stock,
        'trays_sold': weekly_sales.aggregate(total=Sum('trays_sold'))['total'] or 0,
        'total_revenue': round(total_revenue, 2),
        'operating_expenses': round(total_operating_costs, 2),
        'capital_expenses': round(total_capital_expenses, 2),
        'total_expenses': round(total_operating_costs, 2),  # For backward compatibility
        'feed_consumption_cost': round(feed_cost_this_week, 2),
        'other_operating_expenses': round(total_operating_expenses, 2),
        'profit_loss': round(profit_loss, 2),
        'profit_margin': round(profit_margin, 2),
        'feed_efficiency': round(feed_efficiency, 2),
        'avg_eggs_per_hen': round(avg_eggs_per_hen, 2),
        'feed_bought_week': round(feed_bought_week, 2),
        'feed_used_week': round(total_feed_used_kg, 2),
        'feed_remaining': round(feed_remaining, 2)
    }

    return Response(data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sales_history(request):
    """Get sales history"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    # Get date range from query params
    end_date_str = request.GET.get('end_date', datetime.now().date())
    if isinstance(end_date_str, str):
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        end_date = end_date_str

    start_date_str = request.GET.get('start_date')
    if start_date_str:
        if isinstance(start_date_str, str):
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            start_date = start_date_str
    else:
        start_date = end_date - timedelta(days=30)

    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()

    sales = Sale.objects.filter(date__gte=start_date, date__lte=end_date).order_by('-date')

    data = {
        'date_range': {
            'start_date': start_date,
            'end_date': end_date
        },
        'sales': list(sales.values('id', 'date', 'trays_sold', 'price_per_tray', 'total_amount', 'created_at')),
        'summary': {
            'total_sales': sales.count(),
            'total_trays_sold': sales.aggregate(total=Sum('trays_sold'))['total'] or 0,
            'total_revenue': sales.aggregate(total=Sum('total_amount'))['total'] or 0,
            'avg_price_per_tray': sales.aggregate(avg=Avg('price_per_tray'))['avg'] or 0
        }
    }

    return Response(data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def feed_history(request):
    """Get feed purchase and consumption history"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    # Get date range from query params
    end_date = request.GET.get('end_date', datetime.now().date())
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    start_date = request.GET.get('start_date')
    if start_date:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        start_date = end_date - timedelta(days=30)

    purchases = FeedPurchase.objects.filter(date__gte=start_date, date__lte=end_date).order_by('-date')
    consumption = FeedConsumption.objects.filter(date__gte=start_date, date__lte=end_date).order_by('-date')

    data = {
        'date_range': {
            'start_date': start_date,
            'end_date': end_date
        },
        'feed_purchases': list(purchases.values('id', 'date', 'feed_type', 'quantity_kg', 'total_cost', 'cost_per_kg', 'created_at')),
        'feed_consumption': list(consumption.values('id', 'date', 'quantity_used_kg', 'created_at')),
        'summary': {
            'total_purchases': purchases.count(),
            'total_feed_bought': purchases.aggregate(total=Sum('quantity_kg'))['total'] or 0,
            'total_feed_cost': purchases.aggregate(total=Sum('total_cost'))['total'] or 0,
            'total_feed_used': consumption.aggregate(total=Sum('quantity_used_kg'))['total'] or 0,
            'feed_remaining': (purchases.aggregate(total=Sum('quantity_kg'))['total'] or 0) - (consumption.aggregate(total=Sum('quantity_used_kg'))['total'] or 0)
        }
    }

    return Response(data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def expenses_history(request):
    """Get expenses history"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    # Get date range from query params
    end_date_str = request.GET.get('end_date', datetime.now().date())
    if isinstance(end_date_str, str):
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        end_date = end_date_str

    start_date_str = request.GET.get('start_date')
    if start_date_str:
        if isinstance(start_date_str, str):
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            start_date = start_date_str
    else:
        start_date = end_date - timedelta(days=30)

    expenses = Expense.objects.filter(date__gte=start_date, date__lte=end_date).order_by('-date')

    # Group by expense type
    expense_types = expenses.values('expense_type').annotate(
        count=Count('id'),
        total_amount=Sum('amount')
    ).order_by('expense_type')

    data = {
        'date_range': {
            'start_date': start_date,
            'end_date': end_date
        },
        'expenses': list(expenses.values('id', 'date', 'expense_type', 'description', 'amount', 'recorded_by__username', 'created_at')),
        'expense_types': list(expense_types),
        'summary': {
            'total_expenses': expenses.count(),
            'total_amount': expenses.aggregate(total=Sum('amount'))['total'] or 0,
            'avg_expense': expenses.aggregate(avg=Avg('amount'))['avg'] or 0
        }
    }

    return Response(data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_medical(request):
    """Record medical treatment for chickens"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    data = request.data
    chicken_id = data.get('chicken_id')
    date = data.get('date', datetime.now().date())
    treatment_type = data.get('treatment_type')
    description = data.get('description')
    medication = data.get('medication', '')
    dosage = data.get('dosage', '')
    cost = data.get('cost', 0)
    vet_name = data.get('vet_name', '')
    notes = data.get('notes', '')

    if not treatment_type or not description:
        return Response({'detail': 'treatment_type and description are required'}, status=status.HTTP_400_BAD_REQUEST)

    chicken = None
    if chicken_id:
        try:
            chicken = Chicken.objects.get(id=chicken_id, cage__user=request.user)
        except Chicken.DoesNotExist:
            return Response({'detail': 'Chicken not found'}, status=status.HTTP_404_NOT_FOUND)

    MedicalRecord.objects.create(
        chicken=chicken,
        date=date,
        treatment_type=treatment_type,
        description=description,
        medication=medication,
        dosage=dosage,
        cost=cost,
        vet_name=vet_name,
        notes=notes,
        recorded_by=request.user
    )

    return Response({'message': f'Medical record created successfully'}, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detailed_reports(request):
    """Comprehensive farm activity report"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    # Get date from query params, default to today
    report_date = request.GET.get('date', datetime.now().date())
    if isinstance(report_date, str):
        try:
            report_date = datetime.strptime(report_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    # Get date range for weekly/monthly data
    week_start = report_date - timedelta(days=report_date.weekday())
    month_start = report_date.replace(day=1)

    # Basic farm info
    total_cages = Cage.objects.filter(user=request.user).count()
    chicken_setting = FarmSettings.objects.filter(key='total_chickens').first()
    total_chickens = int(chicken_setting.value) if chicken_setting else Chicken.objects.filter(cage__user=request.user).count()

    # Egg production data for the specific date
    eggs_today = Egg.objects.filter(laid_date=report_date).filter(
        Q(chicken__cage__user=request.user) | Q(recorded_by=request.user)
    )

    cage_eggs_today = eggs_today.filter(source='cage').count()
    shade_eggs_today = eggs_today.filter(source='shade').count()
    total_eggs_today = cage_eggs_today + shade_eggs_today

    # Weekly and monthly egg totals
    eggs_week = Egg.objects.filter(laid_date__gte=week_start, laid_date__lte=report_date).filter(
        Q(chicken__cage__user=request.user) | Q(recorded_by=request.user)
    ).count()

    eggs_month = Egg.objects.filter(laid_date__gte=month_start, laid_date__lte=report_date).filter(
        Q(chicken__cage__user=request.user) | Q(recorded_by=request.user)
    ).count()

    # Financial data for the week
    weekly_sales = Sale.objects.filter(date__gte=week_start, date__lte=report_date)
    total_revenue = weekly_sales.aggregate(total=Sum('total_amount'))['total'] or 0

    # Operating expenses (feed consumption + other expenses)
    weekly_feed_consumption = FeedConsumption.objects.filter(date__gte=week_start, date__lte=report_date)
    total_feed_used_kg = weekly_feed_consumption.aggregate(total=Sum('quantity_used_kg'))['total'] or 0

    # Calculate feed cost
    feed_cost_this_week = 0
    if total_feed_used_kg > 0:
        feed_purchases = FeedPurchase.objects.filter(date__gte=week_start - timedelta(days=90), date__lte=report_date)
        if feed_purchases.exists():
            total_cost = 0
            total_qty = 0
            for purchase in feed_purchases:
                if purchase.quantity_kg and purchase.total_cost:
                    total_cost += purchase.total_cost
                    total_qty += purchase.quantity_kg

            if total_qty > 0:
                avg_cost_per_kg = total_cost / total_qty
                feed_cost_this_week = total_feed_used_kg * avg_cost_per_kg

    weekly_expenses = Expense.objects.filter(date__gte=week_start, date__lte=report_date).exclude(expense_type='feed')
    total_operating_expenses = weekly_expenses.aggregate(total=Sum('amount'))['total'] or 0
    total_operating_costs = feed_cost_this_week + total_operating_expenses

    # Profit/Loss
    profit_loss = total_revenue - total_operating_costs

    # Store status
    store, created = Store.objects.get_or_create(id=1, defaults={'trays_in_stock': 0})

    # Feed inventory
    total_feed_bought = FeedPurchase.objects.aggregate(total=Sum('quantity_kg'))['total'] or 0
    total_feed_used = FeedConsumption.objects.aggregate(total=Sum('quantity_used_kg'))['total'] or 0
    feed_remaining = total_feed_bought - total_feed_used

    # Get recent egg collection data for the last 7 days
    recent_eggs = Egg.objects.filter(
        laid_date__gte=report_date - timedelta(days=7),
        laid_date__lte=report_date
    ).filter(
        Q(chicken__cage__user=request.user) | Q(recorded_by=request.user)
    ).order_by('-laid_date')[:10]

    recent_sales = Sale.objects.filter(
        date__gte=report_date - timedelta(days=7),
        date__lte=report_date
    ).order_by('-date')[:5]

    recent_expenses = Expense.objects.filter(
        date__gte=report_date - timedelta(days=7),
        date__lte=report_date
    ).order_by('-date')[:5]

    # Get egg collection records with count aggregation
    egg_collection_records = Egg.objects.filter(
        laid_date__gte=report_date - timedelta(days=7),
        laid_date__lte=report_date
    ).filter(
        Q(chicken__cage__user=request.user) | Q(recorded_by=request.user)
    ).values('laid_date', 'source').annotate(count=Count('id')).order_by('-laid_date')

    # Get sales records
    sales_records = Sale.objects.filter(
        date__gte=report_date - timedelta(days=7),
        date__lte=report_date
    ).values('date', 'trays_sold', 'price_per_tray', 'total_amount').order_by('-date')

    # Get expense records
    expense_records = Expense.objects.filter(
        date__gte=report_date - timedelta(days=7),
        date__lte=report_date
    ).values('date', 'expense_type', 'amount', 'description').order_by('-date')

    # Calculate daily summaries for the week
    daily_summaries = []
    for i in range(7):
        day_date = report_date - timedelta(days=i)
        day_eggs = Egg.objects.filter(laid_date=day_date).filter(
            Q(chicken__cage__user=request.user) | Q(recorded_by=request.user)
        ).count()
        day_sales = Sale.objects.filter(date=day_date).aggregate(
            trays=Sum('trays_sold'),
            revenue=Sum('total_amount')
        )
        day_expenses = Expense.objects.filter(date=day_date).aggregate(total=Sum('amount'))['total'] or 0

        daily_summaries.append({
            'date': day_date.isoformat(),
            'eggs_collected': day_eggs,
            'trays_sold': day_sales['trays'] or 0,
            'revenue': round(day_sales['revenue'] or 0, 2),
            'expenses': round(day_expenses, 2),
            'profit_loss': round((day_sales['revenue'] or 0) - day_expenses, 2),
            'status': 'recorded' if day_eggs > 0 else 'no_data'
        })

    # Compile comprehensive report matching frontend expectations
    data = {
        'date_range': {
            'start_date': (report_date - timedelta(days=7)).isoformat(),
            'end_date': report_date.isoformat()
        },
        'summary_totals': {
            'total_eggs': total_eggs_today,
            'total_trays_sold': weekly_sales.aggregate(total=Sum('trays_sold'))['total'] or 0,
            'total_revenue': round(total_revenue, 2),
            'total_expenses': round(total_operating_costs, 2),
            'total_profit_loss': round(profit_loss, 2)
        },
        'egg_collection_records': list(egg_collection_records),
        'sales_records': list(sales_records),
        'expense_records': list(expense_records),
        'daily_summaries': daily_summaries,
        'farm_overview': {
            'total_cages': total_cages,
            'total_chickens': total_chickens,
            'total_capacity': Cage.objects.aggregate(total=Sum('capacity'))['total'] or 0,
        },
        'egg_production': {
            'today': {
                'total': total_eggs_today,
                'cage_eggs': cage_eggs_today,
                'shade_eggs': shade_eggs_today,
                'trays_produced': total_eggs_today // 30,
                'remaining_eggs': total_eggs_today % 30
            },
            'this_week': eggs_week,
            'this_month': eggs_month,
            'laying_percentage': round((total_eggs_today / total_chickens * 100), 2) if total_chickens > 0 else 0
        },
        'financial_summary': {
            'revenue': round(total_revenue, 2),
            'operating_expenses': round(total_operating_costs, 2),
            'feed_cost': round(feed_cost_this_week, 2),
            'other_expenses': round(total_operating_expenses, 2),
            'profit_loss': round(profit_loss, 2),
            'profit_margin': round((profit_loss / total_revenue * 100), 2) if total_revenue > 0 else 0
        },
        'inventory_status': {
            'trays_in_store': store.trays_in_stock,
            'feed_remaining_kg': round(feed_remaining, 2),
            'feed_used_this_week': round(total_feed_used_kg, 2)
        },
        'recent_activities': {
            'eggs_collected': [
                {
                    'date': egg.laid_date.isoformat(),
                    'source': egg.source,
                    'cage_id': egg.cage_id,
                    'partition': egg.partition_index
                } for egg in recent_eggs
            ],
            'sales': [
                {
                    'date': sale.date.isoformat(),
                    'trays_sold': sale.trays_sold,
                    'price_per_tray': sale.price_per_tray,
                    'total_amount': sale.total_amount
                } for sale in recent_sales
            ],
            'expenses': [
                {
                    'date': expense.date.isoformat(),
                    'type': expense.expense_type,
                    'amount': expense.amount,
                    'description': expense.description
                } for expense in recent_expenses
            ]
        }
    }

    return Response(data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def medical_history(request):
    """Get medical records history"""
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    # Get date range from query params
    end_date_str = request.GET.get('end_date', datetime.now().date())
    if isinstance(end_date_str, str):
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        end_date = end_date_str

    start_date_str = request.GET.get('start_date')
    if start_date_str:
        if isinstance(start_date_str, str):
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            start_date = start_date_str
    else:
        start_date = end_date - timedelta(days=30)

    medical_records = MedicalRecord.objects.filter(
        date__gte=start_date,
        date__lte=end_date
    ).select_related('chicken', 'recorded_by').order_by('-date')

    # Group by treatment type
    treatment_types = medical_records.values('treatment_type').annotate(
        count=Count('id'),
        total_cost=Sum('cost')
    ).order_by('treatment_type')

    data = {
        'date_range': {
            'start_date': start_date,
            'end_date': end_date
        },
        'medical_records': list(medical_records.values(
            'id', 'date', 'treatment_type', 'description', 'medication',
            'dosage', 'cost', 'vet_name', 'notes', 'chicken__tag_id',
            'recorded_by__username', 'created_at'
        )),
        'treatment_types': list(treatment_types),
        'summary': {
            'total_records': medical_records.count(),
            'total_cost': medical_records.aggregate(total=Sum('cost'))['total'] or 0,
            'avg_cost': medical_records.aggregate(avg=Avg('cost'))['avg'] or 0
        }
    }

    return Response(data)

@api_view(['GET'])
def download_egg_collection_table(request):
    """Download egg collection table as PDF"""
    # Check authentication - allow both token auth and query param token
    user = None
    if request.user.is_authenticated:
        user = request.user
    else:
        # Check for token in Authorization header first
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Token '):
            token = auth_header[6:]  # Remove 'Token ' prefix
        else:
            # Check for token in query params (for direct browser access)
            token = request.GET.get('token')

        if token:
            from rest_framework.authtoken.models import Token
            try:
                token_obj = Token.objects.get(key=token)
                user = token_obj.user
            except Token.DoesNotExist:
                return Response({'detail': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({'detail': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    if user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    # Get date from query params, default to today
    collection_date = request.GET.get('date', datetime.now().date())
    if isinstance(collection_date, str):
        try:
            collection_date = datetime.strptime(collection_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    # Get actual egg data from database for the specified date
    eggs = Egg.objects.filter(
        laid_date=collection_date
    ).filter(
        # Include eggs from user's chickens or eggs recorded by this user
        Q(chicken__cage__user=user) | Q(recorded_by=user)
    )

    # Calculate laying percentage and performance comments
    chicken_setting = FarmSettings.objects.filter(key='total_chickens').first()
    total_chickens = int(chicken_setting.value) if chicken_setting else Chicken.objects.filter(cage__user=user).count()

    total_eggs_today = eggs.count()
    laying_percentage = (total_eggs_today / total_chickens * 100) if total_chickens > 0 else 0

    # Generate automatic performance comments based on laying percentage
    if laying_percentage >= 90:
        performance_comment = "Excellent laying performance! Flock is performing exceptionally well."
    elif laying_percentage >= 80:
        performance_comment = "Very good production. Flock health and feed quality are optimal."
    elif laying_percentage >= 70:
        performance_comment = "Good laying percentage. Monitor feed quality and health."
    elif laying_percentage >= 60:
        performance_comment = "Average production. Consider reviewing feed and health management."
    elif laying_percentage >= 50:
        performance_comment = "Below average production. Check for health issues or feed problems."
    elif laying_percentage >= 30:
        performance_comment = "Poor laying performance. Immediate attention to flock health required."
    else:
        performance_comment = "Critical: Very low production. Urgent veterinary attention needed."

    # Organize eggs by cage, partition, and box for the collection table
    cage_data = {}
    shade_eggs = 0

    for egg in eggs:
        if egg.source == 'shade':
            shade_eggs += 1
        elif egg.cage_id is not None and egg.box_number is not None:
            cage_id = egg.cage_id
            partition = egg.partition_index or 0
            box = egg.box_number

            if cage_id not in cage_data:
                cage_data[cage_id] = {}

            if partition not in cage_data[cage_id]:
                cage_data[cage_id][partition] = {}

            if box not in cage_data[cage_id][partition]:
                cage_data[cage_id][partition][box] = 0

            cage_data[cage_id][partition][box] += 1

    # Create PDF buffer
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title with farm name and date
    farm_name = "Joe Farm"
    title_text = f"{farm_name} - Egg Collection Table - {collection_date}"
    title = Paragraph(title_text, styles['Title'])
    title.style.fontSize = 18  # Larger title
    title.style.spaceAfter = 20
    story.append(title)
    story.append(Spacer(1, 12))

    # Performance Summary
    summary_data = [
        ['Date:', str(collection_date)],
        ['Total Eggs Collected:', str(total_eggs_today)],
        ['Total Chickens:', str(total_chickens)],
        ['Laying Percentage:', f"{laying_percentage:.2f}%"],
        ['Performance:', performance_comment],
        ['Trays Produced:', f"{total_eggs_today // 30} full trays + {total_eggs_today % 30} remaining eggs"]
    ]

    summary_table = Table(summary_data, colWidths=[150, 250])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),  # Larger font size for better readability
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    # Get actual cages from database
    user_cages = Cage.objects.filter(user=user).values_list('id', flat=True)
    if not user_cages:
        # If no cages exist, use default cages 1 and 2 for display purposes
        user_cages = [1, 2]

    for cage_id in user_cages:
        cage_info = {
            'front_partition': [],
            'back_partition': []
        }

        # Frontend structure: each cage has front and back partitions
        # Each partition has 4 rows x 4 columns = 16 boxes total
        # Data is stored with partition_index (0=front, 1=back)

        # Front partition (partition_index 0)
        front_data = cage_data.get(cage_id, {}).get(0, {})  # partition_index 0
        for box_num in range(1, 17):  # 16 boxes (4x4 grid)
            count = front_data.get(box_num, 0) if isinstance(front_data, dict) else 0
            cage_info['front_partition'].append({
                'box': box_num,
                'eggs': count
            })

        # Back partition (partition_index 1)
        back_data = cage_data.get(cage_id, {}).get(1, {})  # partition_index 1
        for box_num in range(1, 17):  # 16 boxes (4x4 grid)
            count = back_data.get(box_num, 0) if isinstance(back_data, dict) else 0
            cage_info['back_partition'].append({
                'box': box_num,
                'eggs': count
            })

        cage_info['cage_total'] = sum(p['eggs'] for p in cage_info['front_partition']) + sum(p['eggs'] for p in cage_info['back_partition'])

        # Cage Title
        story.append(Paragraph(f"Cage {cage_id}", styles['Heading2']))
        story.append(Spacer(1, 6))

        # Front Partition Table
        story.append(Paragraph("Front Partition", styles['Heading3']))
        front_data_table = [['Box', '1', '2', '3', '4', '5', '6', '7', '8']]
        for row in range(4):
            row_data = [f'Row {row + 1}']
            for col in range(8):
                box_index = row * 8 + col
                eggs = cage_info['front_partition'][box_index]['eggs'] if box_index < len(cage_info['front_partition']) else 0
                row_data.append(str(eggs))
            front_data_table.append(row_data)

        front_table = Table(front_data_table, colWidths=[40] + [30] * 8)
        front_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),  # Larger font size for better readability
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(front_table)
        story.append(Spacer(1, 12))

        # Back Partition Table
        story.append(Paragraph("Back Partition", styles['Heading3']))
        back_data_table = [['Box', '1', '2', '3', '4', '5', '6', '7', '8']]
        for row in range(4):
            row_data = [f'Row {row + 1}']
            for col in range(8):
                box_index = row * 8 + col
                eggs = cage_info['back_partition'][box_index]['eggs'] if box_index < len(cage_info['back_partition']) else 0
                row_data.append(str(eggs))
            back_data_table.append(row_data)

        back_table = Table(back_data_table, colWidths=[40] + [30] * 8)
        back_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),  # Larger font size for better readability
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(back_table)
        story.append(Spacer(1, 12))

        # Cage Summary
        front_total = sum(p['eggs'] for p in cage_info['front_partition'])
        back_total = sum(p['eggs'] for p in cage_info['back_partition'])
        cage_total = cage_info['cage_total']

        cage_summary_data = [
            ['Front Partition:', str(front_total)],
            ['Back Partition:', str(back_total)],
            ['Cage Total:', str(cage_total)]
        ]

        cage_summary_table = Table(cage_summary_data, colWidths=[120, 80])
        cage_summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.green),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),  # Larger font size for better readability
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgreen),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(cage_summary_table)
        story.append(Spacer(1, 20))

    # Shade Eggs Summary
    shade_summary_data = [
        ['Shade Eggs:', str(shade_eggs)]
    ]

    shade_summary_table = Table(shade_summary_data, colWidths=[120, 80])
    shade_summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.blue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),  # Larger font size for better readability
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(Paragraph("Shade Eggs", styles['Heading2']))
    story.append(shade_summary_table)
    story.append(Spacer(1, 20))

    # Overall Summary
    overall_summary_data = [
        ['Total Cage Eggs:', str(total_eggs_today - shade_eggs)],
        ['Total Shade Eggs:', str(shade_eggs)],
        ['Grand Total:', str(total_eggs_today)],
        ['Laying Percentage:', f"{laying_percentage:.2f}%"],
        ['Performance Comment:', performance_comment]
    ]

    overall_summary_table = Table(overall_summary_data, colWidths=[150, 250])
    overall_summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),  # Larger font size for better readability
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightcyan),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(Paragraph("Overall Summary", styles['Heading2']))
    story.append(overall_summary_table)

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="egg_collection_table_{collection_date}.pdf"'
    return response

@api_view(['GET'])
def download_report(request, report_type):
    """Download reports as PDF"""
    # Check authentication - allow both token auth and query param token
    user = None
    if request.user.is_authenticated:
        user = request.user
    else:
        # Check for token in Authorization header first
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Token '):
            token = auth_header[6:]  # Remove 'Token ' prefix
        else:
            # Check for token in form data (when submitted via form)
            token = request.POST.get('Authorization', '').replace('Token ', '') or request.GET.get('token')

        if token:
            from rest_framework.authtoken.models import Token
            try:
                token_obj = Token.objects.get(key=token)
                user = token_obj.user
            except Token.DoesNotExist:
                return Response({'detail': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({'detail': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)

    if user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)

    # Get date range from query params
    end_date_str = request.GET.get('end_date', datetime.now().date())
    if isinstance(end_date_str, str):
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        end_date = end_date_str

    start_date_str = request.GET.get('start_date')
    if start_date_str:
        if isinstance(start_date_str, str):
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            start_date = start_date_str
    else:
        start_date = end_date - timedelta(days=30)

    # Create PDF buffer
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title with farm name
    farm_name = "Joe Farm"
    title_text = f"{farm_name} - {report_type.title()} Report ({start_date} to {end_date})"
    story.append(Paragraph(title_text, styles['Title']))
    story.append(Spacer(1, 12))

    if report_type == 'sales':
        sales = Sale.objects.filter(date__gte=start_date, date__lte=end_date).order_by('-date')

        # Summary
        summary_data = [
            ['Total Sales:', str(sales.count())],
            ['Total Trays Sold:', str(sales.aggregate(total=Sum('trays_sold'))['total'] or 0)],
            ['Total Revenue:', f"Ksh {sales.aggregate(total=Sum('total_amount'))['total'] or 0}"],
            ['Average Price per Tray:', f"Ksh {sales.aggregate(avg=Avg('price_per_tray'))['avg'] or 0:.2f}"]
        ]

        summary_table = Table(summary_data, colWidths=[200, 200])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 20))

        # Sales table
        if sales.exists():
            sales_data = [['Date', 'Trays Sold', 'Price per Tray', 'Total Amount']]
            for sale in sales:
                sales_data.append([
                    str(sale.date),
                    str(sale.trays_sold),
                    f"Ksh {sale.price_per_tray}",
                    f"Ksh {sale.total_amount}"
                ])

            sales_table = Table(sales_data, colWidths=[100, 80, 120, 120])
            sales_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(sales_table)

    elif report_type == 'expenses':
        expenses = Expense.objects.filter(date__gte=start_date, date__lte=end_date).order_by('-date')
        feed_consumption = FeedConsumption.objects.filter(date__gte=start_date, date__lte=end_date).order_by('-date')

        # Calculate feed consumption costs
        feed_cost_total = 0
        if feed_consumption.exists():
            # Get feed purchases for cost calculation
            feed_purchases = FeedPurchase.objects.filter(date__gte=start_date - timedelta(days=90), date__lte=end_date)
            if feed_purchases.exists():
                total_cost = 0
                total_qty = 0
                for purchase in feed_purchases:
                    if purchase.quantity_kg and purchase.total_cost:
                        total_cost += purchase.total_cost
                        total_qty += purchase.quantity_kg

                if total_qty > 0:
                    avg_cost_per_kg = total_cost / total_qty
                    total_feed_used = feed_consumption.aggregate(total=Sum('quantity_used_kg'))['total'] or 0
                    feed_cost_total = total_feed_used * avg_cost_per_kg

        # Summary with breakdown
        total_expenses_amount = expenses.aggregate(total=Sum('amount'))['total'] or 0
        summary_data = [
            ['Report Period:', f"{start_date} to {end_date}"],
            ['Total Expense Records:', str(expenses.count())],
            ['Operating Expenses (Medicine, Labor, etc.):', f"Ksh {total_expenses_amount:.2f}"],
            ['Feed Consumption Cost:', f"Ksh {feed_cost_total:.2f}"],
            ['Total Operating Costs:', f"Ksh {(total_expenses_amount + feed_cost_total):.2f}"],
            ['Average Daily Operating Cost:', f"Ksh {((total_expenses_amount + feed_cost_total) / ((end_date - start_date).days + 1)):.2f}"]
        ]

        summary_table = Table(summary_data, colWidths=[250, 150])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 20))

        # Operating Expenses table
        if expenses.exists():
            story.append(Paragraph("Operating Expenses (Medicine, Labor, Utilities, etc.)", styles['Heading2']))
            expense_data = [['Date', 'Type', 'Amount', 'Description']]
            for expense in expenses:
                expense_data.append([
                    str(expense.date),
                    expense.expense_type.title(),
                    f"Ksh {expense.amount}",
                    expense.description or ''
                ])

            expense_table = Table(expense_data, colWidths=[80, 80, 100, 200])
            expense_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(expense_table)
            story.append(Spacer(1, 20))

        # Feed Consumption table
        if feed_consumption.exists():
            story.append(Paragraph("Feed Consumption (Daily Operating Costs)", styles['Heading2']))
            feed_data = [['Date', 'Feed Used (kg)', 'Estimated Cost']]
            for cons in feed_consumption:
                # Calculate cost for this specific consumption
                daily_cost = 0
                if feed_purchases.exists() and total_qty > 0:
                    daily_cost = cons.quantity_used_kg * avg_cost_per_kg

                feed_data.append([
                    str(cons.date),
                    f"{cons.quantity_used_kg} kg",
                    f"Ksh {daily_cost:.2f}"
                ])

            feed_table = Table(feed_data, colWidths=[80, 100, 100])
            feed_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(feed_table)

    elif report_type == 'feed':
        purchases = FeedPurchase.objects.filter(date__gte=start_date, date__lte=end_date).order_by('-date')
        consumption = FeedConsumption.objects.filter(date__gte=start_date, date__lte=end_date).order_by('-date')

        # Calculate feed consumption costs for the period
        feed_cost_total = 0
        avg_cost_per_kg = 0
        if consumption.exists() and purchases.exists():
            # Calculate weighted average cost per kg for the period
            total_cost = 0
            total_qty = 0
            for purchase in purchases:
                if purchase.quantity_kg and purchase.total_cost:
                    total_cost += purchase.total_cost
                    total_qty += purchase.quantity_kg

            if total_qty > 0:
                avg_cost_per_kg = total_cost / total_qty
                total_feed_used = consumption.aggregate(total=Sum('quantity_used_kg'))['total'] or 0
                feed_cost_total = total_feed_used * avg_cost_per_kg

        # Summary with clear accounting breakdown
        total_bought = purchases.aggregate(total=Sum('quantity_kg'))['total'] or 0
        total_cost = purchases.aggregate(total=Sum('total_cost'))['total'] or 0
        total_used = consumption.aggregate(total=Sum('quantity_used_kg'))['total'] or 0
        feed_remaining = total_bought - total_used

        # Farm name header
        farm_name = "Joe Farm"
        story.append(Paragraph(f"{farm_name} - Feed Report", styles['Title']))
        story.append(Spacer(1, 12))

        summary_data = [
            ['Report Period:', f"{start_date} to {end_date}"],
            ['CAPITAL EXPENSES (Investments):', ''],
            ['• Feed Purchases (Inventory):', f"{total_bought} kg @ Ksh {total_cost} total"],
            ['• Average Cost per kg:', f"Ksh {avg_cost_per_kg:.2f}"],
            ['OPERATING EXPENSES (Daily Costs):', ''],
            ['• Feed Consumption:', f"{total_used} kg @ Ksh {feed_cost_total:.2f} total"],
            ['• Feed Remaining in Inventory:', f"{feed_remaining} kg"],
            ['Feed Efficiency:', f"{(total_used / total_bought * 100):.1f}%" if total_bought > 0 else 'N/A']
        ]

        summary_table = Table(summary_data, colWidths=[200, 200])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('SPAN', (0, 1), (1, 1)),  # Merge cells for "CAPITAL EXPENSES"
            ('SPAN', (0, 4), (1, 4)),  # Merge cells for "OPERATING EXPENSES"
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 20))

        # Feed purchases table (Capital Expenses)
        if purchases.exists():
            story.append(Paragraph("Feed Purchases (Capital Investment - Not Operating Expenses)", styles['Heading2']))
            purchases_data = [['Date', 'Feed Type', 'Quantity (kg)', 'Total Cost', 'Cost per kg']]
            for purchase in purchases:
                purchases_data.append([
                    str(purchase.date),
                    purchase.feed_type or 'General',
                    str(purchase.quantity_kg),
                    f"Ksh {purchase.total_cost}",
                    f"Ksh {purchase.cost_per_kg:.2f}" if purchase.cost_per_kg else 'N/A'
                ])

            purchases_table = Table(purchases_data, colWidths=[80, 80, 80, 100, 100])
            purchases_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(purchases_table)
            story.append(Spacer(1, 20))

        # Feed consumption table (Operating Expenses)
        if consumption.exists():
            story.append(Paragraph("Feed Consumption (Operating Expenses - Daily Farm Costs)", styles['Heading2']))
            consumption_data = [['Date', 'Feed Used (kg)', 'Cost (Operating Expense)']]
            for cons in consumption:
                daily_cost = cons.quantity_used_kg * avg_cost_per_kg if avg_cost_per_kg > 0 else 0
                consumption_data.append([
                    str(cons.date),
                    str(cons.quantity_used_kg),
                    f"Ksh {daily_cost:.2f}"
                ])

            consumption_table = Table(consumption_data, colWidths=[100, 100, 150])
            consumption_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(consumption_table)
            story.append(Spacer(1, 20))

            # Accounting explanation
            explanation = """
            IMPORTANT ACCOUNTING NOTE:
            • Feed Purchases = CAPITAL EXPENSES (inventory investment, not counted in profit/loss)
            • Feed Consumption = OPERATING EXPENSES (daily costs that affect profit/loss)
            • Profit/Loss = Revenue - Operating Expenses (feed consumption + other daily costs)
            """
            story.append(Paragraph(explanation, styles['Normal']))

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{report_type}_report_{start_date}_to_{end_date}.pdf"'
    return response


# ============ NOTIFICATION ENDPOINTS ============

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_egg_collection_reminder(request):
    """
    Check if egg collection was recorded today.
    Returns a reminder notification if not recorded.
    Timezone: Africa/Nairobi (UTC+3)
    """
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)
    
    # Get today's date in Nairobi timezone
    today = datetime.now().date()
    
    # Check if any eggs were recorded today
    eggs_recorded = Egg.objects.filter(
        laid_date=today,
        recorded_by=request.user
    ).exists()
    
    if eggs_recorded:
        return Response({
            'needs_reminder': False,
            'message': 'Egg collection already recorded for today',
            'date': str(today)
        })
    else:
        return Response({
            'needs_reminder': True,
            'message': '⚠️ Reminder: Egg collection has not been recorded for today. Please record it before end of day.',
            'date': str(today),
            'reminder_type': 'daily_egg_collection'
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def weekly_profit_loss_report(request):
    """
    Generate weekly profit/loss report for notifications.
    Returns summary of revenue, expenses, and profit/loss for the past week.
    """
    if request.user.role != 'owner':
        return Response({'detail': 'Access denied. Owner role required.'}, status=status.HTTP_403_FORBIDDEN)
    
    # Calculate date range (last 7 days, ending yesterday)
    today = datetime.now().date()
    week_end = today - timedelta(days=1)  # Yesterday
    week_start = week_end - timedelta(days=6)  # 7 days ago
    
    # Calculate revenue from sales
    weekly_sales = Sale.objects.filter(date__gte=week_start, date__lte=week_end)
    total_revenue = weekly_sales.aggregate(total=Sum('total_amount'))['total'] or 0
    trays_sold = weekly_sales.aggregate(total=Sum('trays_sold'))['total'] or 0
    
    # Calculate operating expenses
    # 1. Feed consumption costs
    weekly_feed_consumption = FeedConsumption.objects.filter(date__gte=week_start, date__lte=week_end)
    total_feed_used_kg = weekly_feed_consumption.aggregate(total=Sum('quantity_used_kg'))['total'] or 0
    
    feed_cost_this_week = 0
    if total_feed_used_kg > 0:
        feed_purchases = FeedPurchase.objects.filter(date__gte=week_start - timedelta(days=90), date__lte=week_end)
        if feed_purchases.exists():
            total_cost = 0
            total_qty = 0
            for purchase in feed_purchases:
                if purchase.quantity_kg and purchase.total_cost:
                    total_cost += purchase.total_cost
                    total_qty += purchase.quantity_kg
            if total_qty > 0:
                avg_cost_per_kg = total_cost / total_qty
                feed_cost_this_week = total_feed_used_kg * avg_cost_per_kg
    
    # 2. Other operating expenses
    weekly_expenses = Expense.objects.filter(
        date__gte=week_start,
        date__lte=week_end
    ).exclude(expense_type='feed')
    other_expenses = weekly_expenses.aggregate(total=Sum('amount'))['total'] or 0
    
    # Total operating costs
    total_operating_costs = feed_cost_this_week + other_expenses
    
    # Capital expenses (feed purchases)
    weekly_feed_purchases = FeedPurchase.objects.filter(date__gte=week_start, date__lte=week_end)
    capital_expenses = weekly_feed_purchases.aggregate(total=Sum('total_cost'))['total'] or 0
    
    # Profit/Loss (revenue - operating costs)
    profit_loss = total_revenue - total_operating_costs
    profit_margin = (profit_loss / total_revenue * 100) if total_revenue > 0 else 0
    
    # Egg collection for the week
    weekly_eggs = Egg.objects.filter(
        laid_date__gte=week_start,
        laid_date__lte=week_end
    ).count()
    
    # Determine status
    if profit_loss > 0:
        status = 'PROFIT'
        emoji = '📈'
    elif profit_loss < 0:
        status = 'LOSS'
        emoji = '📉'
    else:
        status = 'BREAK-EVEN'
        emoji = '➖'
    
    # Format message for notification
    message = f"""📊 WEEKLY REPORT ({week_start} to {week_end})

{emoji} STATUS: {status}
💰 Revenue: Ksh {total_revenue:,.2f}
🐔 Eggs Collected: {weekly_eggs} eggs
📦 Trays Sold: {trays_sold}

💸 EXPENSES:
• Feed Consumption: Ksh {feed_cost_this_week:,.2f}
• Other: Ksh {other_expenses:,.2f}
• Total Operating: Ksh {total_operating_costs:,.2f}

📌 CAPITAL (Feed Purchases): Ksh {capital_expenses:,.2f}

🏁 NET PROFIT/LOSS: Ksh {profit_loss:,.2f} ({profit_margin:.1f}% margin)
"""
    
    return Response({
        'date_range': {
            'start': str(week_start),
            'end': str(week_end)
        },
        'eggs_collected': weekly_eggs,
        'trays_sold': trays_sold,
        'revenue': round(total_revenue, 2),
        'expenses': {
            'feed_consumption': round(feed_cost_this_week, 2),
            'other': round(other_expenses, 2),
            'total_operating': round(total_operating_costs, 2),
            'capital': round(capital_expenses, 2)
        },
        'profit_loss': round(profit_loss, 2),
        'profit_margin': round(profit_margin, 2),
        'status': status,
        'message': message,
        'notification_type': 'weekly_report'
    })
