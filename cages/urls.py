from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'cages', views.CageViewSet, basename='cage')
router.register(r'chickens', views.ChickenViewSet, basename='chicken')
router.register(r'eggs', views.EggViewSet, basename='egg')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/overview/', views.dashboard_overview, name='dashboard-overview'),
    path('chicken-count/', views.chicken_count, name='chicken-count'),
    path('farm-settings/', views.chicken_count, name='farm-settings'),
    path('store/status/', views.store_status, name='store-status'),
    path('sales/record/', views.record_sale, name='record-sale'),
    path('sales/history/', views.sales_history, name='sales-history'),
    path('feed/purchase/', views.record_feed_purchase, name='record-feed-purchase'),
    path('feed/consumption/', views.record_feed_consumption, name='record-feed-consumption'),
    path('feed/history/', views.feed_history, name='feed-history'),
    path('expenses/record/', views.record_expense, name='record-expense'),
    path('expenses/history/', views.expenses_history, name='expenses-history'),
    path('medical/record/', views.record_medical, name='record-medical'),
    path('medical/history/', views.medical_history, name='medical-history'),
    path('financial/summary/', views.financial_summary, name='financial-summary'),
    path('reports/detailed/', views.detailed_reports, name='detailed-reports'),
    path('reports/egg-collection-table/', views.egg_collection_table, name='egg-collection-table'),
    path('reports/download/<str:report_type>/', views.download_report, name='download-report'),
    path('reports/download/egg-collection-table/', views.download_egg_collection_table, name='download-egg-collection-table'),
    # Notification endpoints
    path('notifications/egg-reminder/', views.check_egg_collection_reminder, name='egg-reminder'),
    path('notifications/weekly-report/', views.weekly_profit_loss_report, name='weekly-report'),
    # Notification API endpoints
    path('notifications/', views.notifications_list, name='notifications-list'),
    path('notifications/unread-count/', views.unread_notification_count, name='unread-notification-count'),
    path('notifications/mark-read/<int:notification_id>/', views.mark_notification_read, name='mark-notification-read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark-all-notifications-read'),
]