from django.db import models

# Create your models here.
class Location(models.Model):
    identifier = models.CharField(max_length=10)
    longitude = models.FloatField()
    latitude = models.FloatField()
    waypoint_id = models.IntegerField(null=True, blank=True, db_index=True)

    def __str__(self):
        return f"{self.identifier} ({self.waypoint_id if self.waypoint_id else 'No ID'})"
    
    
class Route(models.Model):
    identifier = models.CharField(max_length=100, primary_key=True)
    group = models.CharField(max_length=100, blank=True, default='')
    routestring = models.TextField()
    facilities = models.TextField(blank=True, default='')
    tags = models.TextField(blank=True, default='')
    color = models.CharField(max_length=20, blank=True, default='')


class RouteRevisionSet(models.Model):
    number = models.PositiveIntegerField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-number']


class RouteRevisionEntry(models.Model):
    revision = models.ForeignKey(RouteRevisionSet, on_delete=models.CASCADE, related_name='entries')
    identifier = models.CharField(max_length=100)
    group = models.CharField(max_length=100, blank=True, default='')
    routestring = models.TextField()
    facilities = models.TextField(blank=True, default='')
    tags = models.TextField(blank=True, default='')
    color = models.CharField(max_length=20, blank=True, default='')

    class Meta:
        ordering = ['group', 'identifier']
    

class Airway(models.Model):
    identifier = models.CharField(max_length=10, primary_key=True)
    waypoints = models.ManyToManyField(
        Location, 
        through='AirwayWaypoint',
        related_name='airways'
    )

    def get_ordered_waypoints(self):
        return self.waypoints.all().order_by('airwaywaypoint__order')

    def get_coordinates(self):
        points = self.get_ordered_waypoints()
        return [[p.longitude, p.latitude] for p in points]

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