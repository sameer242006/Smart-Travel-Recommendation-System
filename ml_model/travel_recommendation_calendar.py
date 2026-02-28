import pandas as pd
from datetime import date, timedelta
from sqlalchemy import create_engine, text

from ml_model.distance_api import distance_between

# ================= CONFIG =================
DB_URL = "mysql+pymysql://root:root@localhost:3306/weather_project"
engine = create_engine(DB_URL, future=True)

MAX_AI_DAYS = 60
FESTIVAL_WEIGHT = 15

# Average speeds (km/h)
TRANSPORT_SPEEDS = {
    "Car": 80,
    "Bike": 60,
    "Train": 100,
    "Flight": 600
}

# ================= HELPERS =================
def normalize_place(name):
    if not name:
        return None
    name = name.lower().strip()
    if not name.endswith(",in"):
        name += ",in"
    return name.title().replace(",In", ",IN")


def calculate_weather_score(temp, condition, rain_prob):
    score = 0

    # Temperature comfort
    if 18 <= temp <= 28:
        score += 20
    elif 15 <= temp <= 32:
        score += 15
    else:
        score += 8

    # Condition
    if condition in ("Clear", "Cloudy"):
        score += 10
    elif condition == "Rain":
        score -= 8

    # Rain probability
    if rain_prob is not None:
        if rain_prob <= 0.1:
            score += 10
        elif rain_prob <= 0.3:
            score += 4
        elif rain_prob >= 0.6:
            score -= 10

    return score


def travel_time_hours(distance_km, transport_mode):
    if distance_km is None:
        return None
    speed = TRANSPORT_SPEEDS.get(transport_mode, 80)
    hours = distance_km / speed

    # Round to nice human steps (0.5 hour steps)
    return round(hours * 2) / 2


def travel_time_score(hours):
    if hours is None:
        return 0

    if hours <= 3:
        return 15
    elif hours <= 6:
        return 5
    elif hours <= 10:
        return -5
    else:
        return -12


def format_hours(hours):
    if hours is None:
        return "—"
    h = int(hours)
    m = int((hours - h) * 60)
    if h == 0:
        return f"{m} min"
    return f"{h} h {m} min"


# ================= MAIN =================
def recommend_travel(
    start_date,
    end_date,
    travel_type="Solo",
    current_city=None,
    transport_mode="Car",
    max_distance_km=None
):
    today = date.today()

    # ------------------------------------------------
    # DATA SOURCE
    # ------------------------------------------------
    if end_date < today:
        ly_start = start_date - timedelta(days=365)
        ly_end = end_date - timedelta(days=365)

        weather_sql = """
            SELECT name, temp, conditions, precipprob AS rain_prob
            FROM weather_master
            WHERE datetime BETWEEN :start AND :end
            UNION ALL
            SELECT name, temp, conditions, precipprob AS rain_prob
            FROM weather_data
            WHERE datetime BETWEEN :start AND :end
        """
        params = {"start": ly_start, "end": ly_end}
        source_note = "📅 Based on last year historical data"

    elif (end_date - today).days <= MAX_AI_DAYS:
        weather_sql = """
            SELECT name, pred_temp AS temp, conditions, pred_rain_prob AS rain_prob
            FROM weather_predictions
            WHERE predicted_date BETWEEN :start AND :end
        """
        params = {"start": start_date, "end": end_date}
        source_note = "🤖 AI-based weather prediction"

    else:
        ly_start = start_date - timedelta(days=365)
        ly_end = end_date - timedelta(days=365)

        weather_sql = """
            SELECT name, temp, conditions, precipprob AS rain_prob
            FROM weather_master
            WHERE datetime BETWEEN :start AND :end
            UNION ALL
            SELECT name, temp, conditions, precipprob AS rain_prob
            FROM weather_data
            WHERE datetime BETWEEN :start AND :end
        """
        params = {"start": ly_start, "end": ly_end}
        source_note = "📅 Based on last year seasonal data"

    weather_df = pd.read_sql(text(weather_sql), engine, params=params)
    if weather_df.empty:
        return pd.DataFrame(), source_note

    # ------------------------------------------------
    # FESTIVALS
    # ------------------------------------------------
    fest_df = pd.read_sql(
        text("""
            SELECT festival_name, recommended_places
            FROM festivals
            WHERE festival_date BETWEEN :start AND :end
        """),
        engine,
        params={"start": start_date, "end": end_date}
    )

    festival_map = {}
    for _, r in fest_df.iterrows():
        for p in str(r["recommended_places"]).split(","):
            place = normalize_place(p)
            festival_map.setdefault(place, []).append(r["festival_name"])

    # ------------------------------------------------
    # AGGREGATE WEATHER
    # ------------------------------------------------
    agg = (
        weather_df
        .groupby("name")
        .agg(
            avg_temp=("temp", "mean"),
            avg_rain=("rain_prob", "mean"),
            condition=("conditions", lambda x: x.mode().iloc[0])
        )
        .reset_index()
    )

    # ------------------------------------------------
    # SCORING
    # ------------------------------------------------
    results = []

    for _, r in agg.iterrows():
        place = normalize_place(r["name"])

        base_score = calculate_weather_score(r.avg_temp, r.condition, r.avg_rain)
        score = base_score

        dist_km = None
        hours = None

        if current_city:
            dist_km = distance_between(current_city, place)

            # If distance API failed, skip this place
            if dist_km is None:
                continue

            # Distance filter
            if max_distance_km and dist_km > max_distance_km:
                continue

            hours = travel_time_hours(dist_km, transport_mode)
            score += travel_time_score(hours)

        has_festival = place in festival_map
        low_rain = (r.avg_rain is not None and r.avg_rain <= 0.2)
        pleasant_temp = (18 <= r.avg_temp <= 28)
        clear_weather = (r.condition in ("Clear", "Cloudy"))
        warm_place = (r.avg_temp >= 25)

        # Travel type logic
        if travel_type == "Family":
            if pleasant_temp:
                score += 10
            if hours is not None and hours <= 6:
                score += 10

        elif travel_type == "Honeymoon":
            if has_festival:
                score += 20
            if clear_weather:
                score += 15

        elif travel_type == "Friends":
            if warm_place:
                score += 15
            if has_festival:
                score += 10

        elif travel_type == "Solo":
            if low_rain:
                score += 8
            if pleasant_temp:
                score += 6

        if has_festival:
            score += FESTIVAL_WEIGHT

        reasons = []
        if pleasant_temp:
            reasons.append("Pleasant temperature")
        if low_rain:
            reasons.append("Low chance of rain")
        if hours is not None:
            if hours <= 3:
                reasons.append(f"Short travel time by {transport_mode}")
            elif hours <= 6:
                reasons.append(f"Moderate travel time by {transport_mode}")
            else:
                reasons.append(f"Long journey by {transport_mode}")
        if has_festival:
            reasons.append("Festival: " + ", ".join(festival_map[place]))

        results.append({
            "Place": place,
            "Distance (km)": round(dist_km, 1),
            "Travel Time": format_hours(hours),
            "Avg Temp (°C)": round(r.avg_temp, 1),
            "Condition": r.condition,
            "Avg Rain": round(r.avg_rain, 3) if r.avg_rain is not None else None,
            "Festival": ", ".join(festival_map.get(place, [])),
            "Score": round(score, 2),
            "Why recommended?": ", ".join(reasons)
        })

    if not results:
        return pd.DataFrame(), source_note

    df = pd.DataFrame(results).sort_values("Score", ascending=False).head(15)
    return df, source_note