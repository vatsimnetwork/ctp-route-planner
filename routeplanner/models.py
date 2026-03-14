from django.contrib.postgres.fields import ArrayField
from django.db import models

# Create your models here.
class Location(models.Model):
    identifier = models.CharField()
    longitude = models.FloatField()
    latitude = models.FloatField()


class Airway(models.Model):
    identifier = models.CharField(max_length=10, primary_key=True)
    waypoints = models.ManyToManyField(
        Location, 
        through='AirwayWaypoint',
        related_name='airways'
    )

    def __str__(self):
        return self.identifier

class AirwayWaypoint(models.Model):
    airway = models.ForeignKey(Airway, on_delete=models.CASCADE)
    waypoint = models.ForeignKey(Location, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order']
        unique_together = ('airway', 'order')



#class RouteSegement(models.Model):
#    identifier = models.CharField(primary_key=True)
#    routestring = models.CharField()
#    segment = ArrayField(models.ForeignKey(Location, on_delete=models.CASCADE))