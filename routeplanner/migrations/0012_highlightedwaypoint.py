from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('routeplanner', '0011_route_enabled_routerevisionentry_enabled'),
    ]

    operations = [
        migrations.CreateModel(
            name='HighlightedWaypoint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifier', models.CharField(max_length=10, unique=True)),
                ('color', models.CharField(default='#f97316', max_length=7)),
                ('note', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Highlighted Waypoint',
                'verbose_name_plural': 'Highlighted Waypoints',
                'ordering': ['identifier'],
            },
        ),
    ]
