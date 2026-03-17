from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('routeplanner', '0006_route_group_facilities_tags'),
    ]

    operations = [
        migrations.CreateModel(
            name='RouteRevisionSet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.PositiveIntegerField(unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-number'],
            },
        ),
        migrations.CreateModel(
            name='RouteRevisionEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifier', models.CharField(max_length=100)),
                ('group', models.CharField(blank=True, default='', max_length=100)),
                ('routestring', models.TextField()),
                ('facilities', models.TextField(blank=True, default='')),
                ('tags', models.TextField(blank=True, default='')),
                ('revision', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='entries', to='routeplanner.routerevisionset')),
            ],
            options={
                'ordering': ['group', 'identifier'],
            },
        ),
    ]