# scripts/fetch_today_all_places_simple.py

import json
import requests
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

# ================= CONFIG =================
with open("config/credentials.json") as f:
    creds = json.load(f)

API_KEY = creds["api_key"]
mysql = creds["mysql"]

DB_URL = (
    f"mysql+pymysql://{mysql['user']}:{mysql['password']}"
    f"@{mysql['host']}:{mysql['port']}/{mysql['database']}"
)

engine = create_engine(DB_URL, future=True)

# ================= ALL PLACES =================
PLACES = [
    "Manali,IN", "Shimla,IN", "Auli,IN", "Gulmarg,IN", "Leh,IN",
    "Udaipur,IN", "Mount Abu,IN", "Rishikesh,IN", "Nainital,IN", "Kutch,IN",
    "Ooty,IN", "Coorg,IN", "Munnar,IN", "Kodaikanal,IN", "Darjeeling,IN",
    "Mahabaleshwar,IN", "Gangtok,IN", "Shillong,IN", "Tawang,IN", "Kerala,IN",
    "Goa,IN", "Lonavala,IN", "Cherrapunji,IN", "Wayanad,IN", "Konkan,IN",
    "Mussoorie,IN", "Panchgani,IN", "Varanasi,IN", "Mathura,IN", "Vrindavan,IN",
    "Agra,IN", "Amritsar,IN", "Belur Math,IN", "Ayodhya,IN", "Bodh Gaya,IN",
    "Sarnath,IN", "Puri,IN", "Bhubaneswar,IN", "Udupi,IN", "Shantiniketan,IN",
]

# ================= DATE RANGE =================
today = datetime.today().strftime("%Y-%m-%d")
START_DATE = today
END_DATE = today

# ================= HELPERS =================
def g(d, k):
    return d.get(k)

def to_json(v):
    return json.dumps(v) if isinstance(v, (list, dict)) else v

# ================= FETCH & STORE =================
for place in PLACES:
    print(f"Fetching {place}")

    url = (
        f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/"
        f"timeline/{place}/{START_DATE}/{END_DATE}"
        f"?unitGroup=metric&key={API_KEY}&include=days&contentType=json"
    )

    res = requests.get(url, timeout=30)
    res.raise_for_status()
    data = res.json()

    rows = []

    for day in data["days"]:
        rows.append({
            "name": place,
            "datetime": day["datetime"],

            "temp": g(day, "temp"),
            "tempmax": g(day, "tempmax"),
            "tempmin": g(day, "tempmin"),

            "feelslike": g(day, "feelslike"),
            "feelslikemax": g(day, "feelslikemax"),
            "feelslikemin": g(day, "feelslikemin"),

            "dew": g(day, "dew"),
            "humidity": g(day, "humidity"),

            "precip": g(day, "precip"),
            "precipprob": g(day, "precipprob"),
            "precipcover": g(day, "precipcover"),
            "preciptype": to_json(g(day, "preciptype")),

            "sealevelpressure": g(day, "sealevelpressure"),
            "severerisk": g(day, "severerisk"),

            "snow": g(day, "snow"),
            "snowdepth": g(day, "snowdepth"),

            "cloudcover": g(day, "cloudcover"),
            "conditions": g(day, "conditions"),
            "description": g(day, "description"),
            "icon": g(day, "icon"),

            "stations": to_json(g(day, "stations")),

            "solarradiation": g(day, "solarradiation"),
            "solarenergy": g(day, "solarenergy"),
            "uvindex": g(day, "uvindex"),

            "visibility": g(day, "visibility"),
            "winddir": g(day, "winddir"),
            "windgust": g(day, "windgust"),
            "windspeed": g(day, "windspeed"),

            "sunrise": g(day, "sunrise"),
            "sunset": g(day, "sunset"),
            "moonphase": g(day, "moonphase"),

            "source": "visualcrossing"
        })

    df = pd.DataFrame(rows)

    # Delete old records for same place & date
    with engine.begin() as conn:
        conn.execute(
            text("""
                DELETE FROM weather_data
                WHERE name = :name
                  AND datetime BETWEEN :start AND :end
            """),
            {"name": place, "start": START_DATE, "end": END_DATE}
        )

    # Insert new records
    df.to_sql("weather_data", engine, if_exists="append", index=False)

    print(f"{place} saved")

print("\nALL PLACES STORED IN ONE TABLE")