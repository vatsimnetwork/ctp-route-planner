from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('routeplanner', '0005_location_waypoint_id_alter_location_identifier'),
    ]

    operations = [
        migrations.RenameField(
            model_name='route',
            old_name='type',
            new_name='group',
        ),
        migrations.AlterField(
            model_name='route',
            name='identifier',
            field=models.CharField(max_length=100, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='route',
            name='group',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='route',
            name='routestring',
            field=models.TextField(),
        ),
        migrations.AddField(
            model_name='route',
            name='facilities',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='route',
            name='tags',
            field=models.TextField(blank=True, default=''),
        ),
    ]