import hashlib
import logging
from datetime import date
from types import SimpleNamespace

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 10


def _stable_id_for_identifier(identifier: str) -> int:
    digest = hashlib.sha256(identifier.encode()).digest()
    return int.from_bytes(digest[:6], 'big')


def _waypoint_id(wp) -> int:
    if wp.waypoint_id is not None:
        return wp.waypoint_id
    return wp.id


def resolve_route_to_locations(normalized_route: str, caches: dict) -> list:
    from routeplanner.views.routeplotter import (
        DIRECT_ROUTE_TOKENS,
        check_for_oceanic_waypoint,
        get_airway_waypoints,
        resolve_token,
    )

    resolved = []
    prev_location = None

    for token in normalized_route.split():
        token_upper = token.upper()
        if token_upper in DIRECT_ROUTE_TOKENS:
            continue

        oceanic = check_for_oceanic_waypoint(token_upper)
        if oceanic:
            lat, lon = oceanic
            resolved.append({
                'type': 'oceanic',
                'identifier': token_upper,
                'latitude': lat,
                'longitude': lon,
                'waypoint_id': _stable_id_for_identifier(token_upper),
                'location': None,
            })
            prev_location = None
            continue

        result = resolve_token(
            token_upper,
            prev_location,
            location_candidates_by_upper=caches.get('location_candidates_by_upper', {}),
            airway_by_upper=caches.get('airway_by_upper', {}),
            airway_waypoints_by_upper=caches.get('airway_waypoints_by_upper', {}),
        )
        if result:
            if result['type'] == 'waypoint':
                wp = result['waypoint']
                resolved.append({
                    'type': 'waypoint',
                    'identifier': result['identifier'],
                    'latitude': result['lat'],
                    'longitude': result['lon'],
                    'waypoint_id': _waypoint_id(wp),
                    'location': wp,
                })
                prev_location = wp
            else:
                resolved.append({'type': 'airway', 'identifier': result['identifier'], 'location': None})

    locations = []
    sort_order = 0
    for i, item in enumerate(resolved):
        if item['type'] in ('waypoint', 'oceanic'):
            locations.append({
                'identifier': item['identifier'],
                'latitude': item['latitude'],
                'longitude': item['longitude'],
                'waypointId': item['waypoint_id'],
                'sortOrder': sort_order,
            })
            sort_order += 1
        elif item['type'] == 'airway':
            prev_wp = next((r for r in reversed(resolved[:i]) if r['type'] == 'waypoint' and r['location']), None)
            next_wp = next((r for r in resolved[i + 1:] if r['type'] == 'waypoint' and r['location']), None)
            if prev_wp and next_wp:
                airway_wps = get_airway_waypoints(
                    item['identifier'],
                    prev_wp['location'],
                    next_wp['location'],
                    caches.get('airway_waypoints_by_upper', {}),
                )
                for wp in airway_wps[1:-1]:
                    locations.append({
                        'identifier': wp.identifier,
                        'latitude': wp.latitude,
                        'longitude': wp.longitude,
                        'waypointId': _waypoint_id(wp),
                        'sortOrder': sort_order,
                    })
                    sort_order += 1

    return locations


def _headers():
    return {'X-API-Key': settings.CTP_API_KEY, 'Content-Type': 'application/json'}


def _url(path):
    return f'{settings.CTP_API_URL}/api{path}'


def _segment_to_route(seg):
    tags = seg.get('tags') or []
    tag_str = ' '.join(sorted(t.get('tag', '') for t in tags if t.get('tag')))
    return SimpleNamespace(
        api_id=seg.get('id', 0),
        identifier=seg.get('identifier', ''),
        group=seg.get('routeSegmentGroup', ''),
        routestring=seg.get('routeString', ''),
        facilities=seg.get('facilities', ''),
        tags=tag_str,
        color=seg.get('color', ''),
        enabled=seg.get('enabled', True),
    )


def _route_to_segment(route_data, api_id=0, event_id=None, locations=None, route_revision=0):
    tags_str = route_data.get('tags', '')
    tags = [{'tag': t} for t in tags_str.split() if t] if tags_str else []
    seg = {
        'identifier': route_data.get('identifier', ''),
        'routeSegmentGroup': route_data.get('group', ''),
        'routeString': route_data.get('routestring', ''),
        'facilities': route_data.get('facilities', ''),
        'color': route_data.get('color', ''),
        'enabled': route_data.get('enabled', True),
        'tags': tags,
        'locations': locations or [],
        'routeRevision': route_revision,
    }
    if api_id:
        seg['id'] = api_id
    if event_id:
        seg['eventId'] = event_id
    return seg


def get_events():
    resp = requests.get(_url('/events'), headers=_headers(), timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_latest_event_id():
    events = get_events()
    if not events:
        return None
    events_sorted = sorted(events, key=lambda e: e.get('date', ''), reverse=True)
    return events_sorted[0].get('id')


def get_or_create_event():
    events = get_events()
    if events:
        events_sorted = sorted(events, key=lambda e: e.get('date', ''), reverse=True)
        return events_sorted[0]
    payload = {
        'title': 'CTP Event',
        'date': date.today().isoformat() + 'T00:00:00Z',
    }
    resp = requests.post(_url('/events'), headers=_headers(), json=payload, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def list_routes(event_id):
    resp = requests.get(_url(f'/events/{event_id}/route-segments'), headers=_headers(), timeout=_TIMEOUT)
    resp.raise_for_status()
    return [_segment_to_route(s) for s in resp.json()]


def get_latest_slot_revision(event_id):
    resp = requests.get(_url(f'/events/{event_id}/slot-revisions/latest'), headers=_headers(), timeout=_TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def get_slot_draft_entries(revision_id):
    resp = requests.get(_url(f'/slot-revisions/{revision_id}/draft-entries'), headers=_headers(), timeout=_TIMEOUT)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json()


def batch_save_routes(event_id, updates, deletes):
    for seg in updates:
        seg['eventId'] = event_id
    payload = {
        'updates': updates,
        'deletes': deletes,
    }
    resp = requests.post(_url('/route-segments/save'), headers=_headers(), json=payload, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def create_route_revision(event_id):
    resp = requests.post(
        _url(f'/route-revisions?eventId={event_id}'),
        headers=_headers(),
        json={},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get('number', 0)


def latest_revision_number():
    resp = requests.get(_url('/route-revisions'), headers=_headers(), timeout=_TIMEOUT)
    resp.raise_for_status()
    revisions = resp.json()
    if revisions:
        return revisions[0].get('number', 0)
    return 0


def list_custom_fixes():
    resp = requests.get(_url('/custom-fixes'), headers=_headers(), timeout=_TIMEOUT)
    resp.raise_for_status()
    fixes = resp.json()
    return [SimpleNamespace(
        id=f.get('id', 0),
        identifier=f.get('identifier', ''),
        latitude=f.get('latitude', 0),
        longitude=f.get('longitude', 0),
        note=f.get('note', ''),
        created_at=f.get('createdAt', ''),
    ) for f in fixes]


def upsert_custom_fix(identifier, latitude, longitude, note=''):
    payload = {
        'identifier': identifier,
        'latitude': latitude,
        'longitude': longitude,
        'note': note,
    }
    resp = requests.post(_url('/custom-fixes'), headers=_headers(), json=payload, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def delete_custom_fix(identifier):
    resp = requests.delete(_url(f'/custom-fixes/{identifier}'), headers=_headers(), timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def list_highlighted_waypoints():
    resp = requests.get(_url('/highlighted-waypoints'), headers=_headers(), timeout=_TIMEOUT)
    resp.raise_for_status()
    wps = resp.json()
    return [SimpleNamespace(
        id=w.get('id', 0),
        identifier=w.get('identifier', ''),
        color=w.get('color', '#f97316'),
        note=w.get('note', ''),
        created_at=w.get('createdAt', ''),
    ) for w in wps]


def upsert_highlighted_waypoint(identifier, color, note='', waypoint_id=None, latitude=None, longitude=None):
    payload = {
        'identifier': identifier,
        'color': color,
        'note': note,
    }
    if waypoint_id is not None and latitude is not None and longitude is not None:
        payload['waypointId'] = waypoint_id
        payload['latitude'] = latitude
        payload['longitude'] = longitude
    resp = requests.post(_url('/highlighted-waypoints'), headers=_headers(), json=payload, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def delete_highlighted_waypoint(identifier):
    resp = requests.delete(_url(f'/highlighted-waypoints/{identifier}'), headers=_headers(), timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def route_to_segment_payload(route_data, api_id=0, event_id=None, locations=None, route_revision=0):
    return _route_to_segment(route_data, api_id, event_id, locations, route_revision)


def list_geojson_overlays():
    resp = requests.get(_url('/geo-json-overlays'), headers=_headers(), timeout=_TIMEOUT)
    resp.raise_for_status()
    overlays = resp.json()
    return [SimpleNamespace(
        id=o.get('id', 0),
        name=o.get('name', ''),
        url=o.get('url', ''),
    ) for o in overlays]


def upsert_geojson_overlay(name, url):
    payload = {
        'name': name,
        'url': url,
    }
    resp = requests.post(_url('/geo-json-overlays'), headers=_headers(), json=payload, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def delete_geojson_overlay(id):
    resp = requests.delete(_url(f'/geo-json-overlays/{id}'), headers=_headers(), timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_event_with_slots(event_id):
    resp = requests.get(
        _url(f'/events/{event_id}/simulator-data/latest-with-slots'),
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def get_slots_window(event_id):
    resp = requests.get(
        _url(f'/events/{event_id}/slots/window'),
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def get_slot_positions_at(event_id, timestamp_iso):
    resp = requests.get(
        _url(f'/events/{event_id}/slot-positions'),
        headers=_headers(),
        params={'timestamp': timestamp_iso},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def get_all_slot_positions(event_id):
    resp = requests.get(
        _url(f'/events/{event_id}/slot-positions/all'),
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
