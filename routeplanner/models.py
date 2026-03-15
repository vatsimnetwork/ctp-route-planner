from django.contrib.postgres.fields import ArrayField
from django.db import models

# Create your models here.
class Location(models.Model):
    identifier = models.CharField()
    longitude = models.FloatField()
    latitude = models.FloatField()


ROUTE_TYPE_CHOICES = [
    ("AMAS", "AMAS"),
    ("EMEA", "EMEA"),
    ("NAT", "NAT"),
]

LEGACY_ROUTE_TYPE_MAP = {
    "AMERICAN": "AMAS",
    "EUROPE": "EMEA",
    "NAT": "NAT",
    "AMAS": "AMAS",
    "EMEA": "EMEA",
}


def normalize_route_type(route_type):
    return LEGACY_ROUTE_TYPE_MAP.get((route_type or "").strip().upper(), "")


def build_route_identifier_base(routestring):
    waypoints = [part.strip().upper() for part in (routestring or "").split() if part.strip()]
    if not waypoints:
        return ""

    start_waypoint = waypoints[0]
    end_waypoint = waypoints[-1]
    return f"{start_waypoint}_{end_waypoint}"


def build_unique_route_identifier(routestring, reserved_identifiers, current_identifier=None):
    base_identifier = build_route_identifier_base(routestring)
    if not base_identifier:
        return ""

    taken_identifiers = set(reserved_identifiers)
    if current_identifier:
        taken_identifiers.discard(current_identifier)

    suffix = 1
    candidate = f"{base_identifier}_{suffix}"
    while candidate in taken_identifiers:
        suffix += 1
        candidate = f"{base_identifier}_{suffix}"

    return candidate


class Route(models.Model):
    identifier = models.CharField(primary_key=True)
    routestring = models.CharField()
    type = models.CharField(max_length=20, choices=ROUTE_TYPE_CHOICES)
    

#class Airway(models.Model):
#    identifier = models.CharField(max_length=10, primary_key=True)
#    waypoints = models.ManyToManyField(
#        Location, 
#        through='AirwayWaypoint',
#        related_name='airways'
#    )

#    def __str__(self):
#        return self.identifier

#class AirwayWaypoint(models.Model):
#    airway = models.ForeignKey(Airway, on_delete=models.CASCADE)
#    waypoint = models.ForeignKey(Location, on_delete=models.CASCADE)
#    order = models.PositiveIntegerField()
#
#    class Meta:
#        ordering = ['order']
#        unique_together = ('airway', 'order')



#class RouteSegement(models.Model):
#    identifier = models.CharField(primary_key=True)
#    routestring = models.CharField()
#    segment = ArrayField(models.ForeignKey(Location, on_delete=models.CASCADE))