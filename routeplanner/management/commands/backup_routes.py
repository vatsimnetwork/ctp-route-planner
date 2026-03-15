import csv
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from routeplanner.models import Route


class Command(BaseCommand):
    help = "Exports all routes to a timestamped CSV file in the backups/ directory."

    def handle(self, *args, **options):
        backup_dir = Path(settings.BASE_DIR) / "backups"
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = backup_dir / f"routes_{timestamp}.csv"

        routes = Route.objects.all().order_by("type", "identifier")

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["identifier", "type", "routestring"])
            for route in routes:
                writer.writerow([route.identifier, route.type, route.routestring])

        self.stdout.write(
            self.style.SUCCESS(f"Backup saved: {filename} ({routes.count()} routes)")
        )
