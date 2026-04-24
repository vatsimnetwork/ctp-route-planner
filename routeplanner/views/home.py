from django.shortcuts import render




import requests
import re
from datetime import datetime, timezone
from django.http import JsonResponse
from shapely.geometry import shape, Point

GEOJSON_URL = 'https://github.com/vatsimnetwork/vatspy-data-project/blob/master/Boundaries.geojson?raw=true'
VATSIM_DATA_URL = 'https://data.vatsim.net/v3/vatsim-data.json'
ATLANTIK_FIRS = ["EGGX", "CZQX", "LPPO", "GVSC", "KZWY", "BIRD", "TTZP", "SBAO"]

try:
    geojson_res = requests.get(GEOJSON_URL).json()
    OCEANIC_FIRS = [
        {
            "id": f['properties'].get('id'),
            "geometry": shape(f['geometry'])
        }
        for f in geojson_res['features']
        if f['properties'].get('id') in ATLANTIK_FIRS
    ]
except Exception:
    OCEANIC_FIRS = []

def is_real_oceanic_route(route):
    if not route: return False
    oceanic_pattern = r"(\d{2,4}[N|S]\d{3}[W|E])|(\d{4}[N|S])|(\d{2}\/\d{2})"
    gateways = ["DOGAL", "MALOT", "NATAL", "PIKIL", "GOMUP", "RESNO", "LIMRI", "TUSKA"]
    return bool(re.search(oceanic_pattern, route)) or any(gw in route for gw in gateways)


def is_water_level_pilot(pilot):
    alt = pilot.get('altitude') or 0
    gs = pilot.get('groundspeed') or 0
    on_ground = pilot.get('on_ground')
    return (not bool(on_ground)) and (alt <= 500 and gs <= 80)


def get_atlantic_fir_id(point):
    for fir in OCEANIC_FIRS:
        if fir["geometry"].contains(point):
            return fir["id"]
    return None

NATTRAK_BOOKINGS_URL = 'https://ctp.vatsim.net/api/bookings-nattrak'

def home(request):
    try:
        data = requests.get(VATSIM_DATA_URL).json()
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    # Fetch booked CIDs from the CTP NatTrak bookings API.
    # Only pilots with a confirmed slot should appear in the stats.
    try:
        bookings_data = requests.get(NATTRAK_BOOKINGS_URL, timeout=10).json()
        booked_cids = {int(b['user_id']) for b in bookings_data.get('data', []) if b.get('user_id')}
    except Exception:
        booked_cids = set()

    pilots = data.get('pilots', [])
    now = datetime.now(timezone.utc)
    
    stats = {
        "global_online": sum(1 for p in pilots if p.get('cid') in booked_cids),
        "atlantik_schwimmer_count": 0,
        "atlantik_route_count": 0,
        "planned_oceanic_flights_count": 0,
        "atlantik_details": {
            "schnellster": {"gs": -1, "callsign": None, "pilot": None},
            "langsamster": {"gs": 999, "callsign": None, "pilot": None},
            "am_hoechsten": {"alt": -1, "callsign": None, "pilot": None},
            "am_niedrigsten": {"alt": 99999, "callsign": None, "pilot": None},
            "dauer_rekord": {"stunden": 0, "callsign": None, "pilot": None},
            "flugzeug_typen": {}
        }
    }

    for p in pilots:
        lat, lon = p.get('latitude'), p.get('longitude')
        if lat is None or lon is None: continue

        # Only include pilots with a confirmed CTP slot.
        pilot_cid = p.get('cid')
        has_slot = pilot_cid in booked_cids
        if not has_slot:
            continue

        punkt = Point(lon, lat)
        atlantic_fir_id = get_atlantic_fir_id(punkt)
        is_in_fir = atlantic_fir_id is not None
        
        fp = p.get('flight_plan') or {}
        route = fp.get('route', '')
        ac_type = fp.get('aircraft_short', 'Unknown')
        has_atlantic_waypoint = is_real_oceanic_route(route)

        if has_atlantic_waypoint:
            stats["planned_oceanic_flights_count"] += 1

        if is_in_fir and has_atlantic_waypoint:
            stats["atlantik_route_count"] += 1

        if is_in_fir and is_water_level_pilot(p):
            stats["atlantik_schwimmer_count"] += 1

        if is_in_fir and has_atlantic_waypoint:
            callsign, pilot_id = p.get('callsign'), p.get('cid')
            gs, alt = p.get('groundspeed', 0), p.get('altitude', 0)

            if gs > 100:
                if gs > stats["atlantik_details"]["schnellster"]["gs"]:
                    stats["atlantik_details"]["schnellster"] = {"gs": gs, "callsign": callsign, "pilot": pilot_id}
                if gs < stats["atlantik_details"]["langsamster"]["gs"]:
                    stats["atlantik_details"]["langsamster"] = {"gs": gs, "callsign": callsign, "pilot": pilot_id}

            if alt > stats["atlantik_details"]["am_hoechsten"]["alt"]:
                stats["atlantik_details"]["am_hoechsten"] = {"alt": alt, "callsign": callsign, "pilot": pilot_id}
            if alt < stats["atlantik_details"]["am_niedrigsten"]["alt"]:
                stats["atlantik_details"]["am_niedrigsten"] = {"alt": alt, "callsign": callsign, "pilot": pilot_id}

            logon_str = p.get('logon_time')
            if logon_str:
                logon_time = datetime.fromisoformat(logon_str.replace('Z', '+00:00'))
                stunden = (now - logon_time).total_seconds() / 3600
                if stunden > stats["atlantik_details"]["dauer_rekord"]["stunden"]:
                    stats["atlantik_details"]["dauer_rekord"] = {"stunden": round(stunden, 2), "callsign": callsign, "pilot": pilot_id}

            stats["atlantik_details"]["flugzeug_typen"][ac_type] = stats["atlantik_details"]["flugzeug_typen"].get(ac_type, 0) + 1

    return render(request, 'home.html', {'stats': stats})


home.login_not_required = True