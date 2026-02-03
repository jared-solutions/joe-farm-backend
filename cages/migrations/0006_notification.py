# Generated migration for Notification model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0004_user_is_approved_created_at'),
        ('cages', '0007_expense_recorded_by_medicalrecord'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notification_type', models.CharField(choices=[('egg_collection', 'Egg Collection'), ('expense', 'Expense Recorded'), ('system', 'System Notification')], max_length=50)),
                ('title', models.CharField(max_length=200)),
                ('message', models.TextField()),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='authentication.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
