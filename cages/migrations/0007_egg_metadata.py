# Generated migration for adding metadata field to Egg model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cages', '0006_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='egg',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
