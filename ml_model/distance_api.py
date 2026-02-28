import math
import time
import json
import os
import requests

# -------------------------------
# FILE-BASED CACHE CONFIG
# -------------------------------
CACHE_FILE = os.path.join(os.path.dirname(__file__), "geo_cache.json")

# Load cache from file if exists
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            _GEO_CACHE = json.load(f)
            # keys are strings, values are [lat, lon]
    except Exception:
        _GEO_CACHE = {}
else:
    _GEO_CACHE = {}


def _save_cache():
    """Save cache to file"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_GEO_CACHE, f, indent=2)
    except Exception as e:
        print("Failed to save geo cache:", e)


def get_coordinates(place_name):
    """
    Fetch latitude & longitude for a place using OpenStreetMap Nominatim API
    Uses file-based cache to avoid repeated API calls.
    """
    if not place_name:
        return None

    key = place_name.lower().strip()

    # 1️⃣ Check cache first
    if key in _GEO_CACHE:
        lat, lon = _GEO_CACHE[key]
        return float(lat), float(lon)

    # 2️⃣ Call API if not in cache
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": place_name,
            "format": "json",
            "limit": 1
        }
        headers = {
            # Better User-Agent to reduce blocking
            "User-Agent": "SameerWeatherProject/1.0 (contact: choudharysameerg@gmail.com.com)"
        }

        r = requests.get(url, params=params, headers=headers, timeout=20)

        if r.status_code != 200:
            print(f"Geocoding HTTP error: {r.status_code} {place_name}")
            return None

        data = r.json()
        if not data:
            print("No geocoding result for", place_name)
            return None

        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])

        # 3️⃣ Save to cache (memory + file)
        _GEO_CACHE[key] = [lat, lon]
        _save_cache()

        # Respect free API rate limit (important!)
        time.sleep(0.2)

        return lat, lon

    except Exception as e:
        print("Geocoding error for", place_name, e)
        return None


def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two lat/lon points in KM
    """
    R = 6371.0  # Earth radius in km

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def distance_between(place_a, place_b):
    """
    Get distance in KM between two place names
    """
    coords_a = get_coordinates(place_a)
    coords_b = get_coordinates(place_b)

    if coords_a is None or coords_b is None:
        return None

    lat1, lon1 = coords_a
    lat2, lon2 = coords_b

    return round(haversine(lat1, lon1, lat2, lon2), 1)