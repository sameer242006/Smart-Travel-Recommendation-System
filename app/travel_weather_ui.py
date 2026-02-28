import sys
import os
from datetime import date
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

# -------------------------------------------------
# PATH FIX
# -------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ml_model.travel_recommendation_calendar import recommend_travel

# -------------------------------------------------
# DB CONFIG
# -------------------------------------------------
DB_URL = "mysql+pymysql://root:root@localhost:3306/weather_project"
engine = create_engine(DB_URL, future=True)

# -------------------------------------------------
# STREAMLIT CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Travel & Weather Recommendation System",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Travel & Weather Recommendation System")

tabs = st.tabs(["✈️ Travel Recommendation", "🌦 Weather Prediction"])

# -------------------------------------------------
# LOAD ALL PLACES
# -------------------------------------------------
places_df = pd.read_sql(
    """
    SELECT DISTINCT name FROM weather_master
    UNION
    SELECT DISTINCT name FROM weather_data
    ORDER BY name
    """,
    engine
)
ALL_PLACES = places_df["name"].tolist()

TRANSPORT_ICONS = {
    "Car": "🚗",
    "Bike": "🏍️",
    "Train": "🚆",
    "Flight": "✈️"
}

# =================================================
# ✈️ TRAVEL RECOMMENDATION TAB
# =================================================
with tabs[0]:
    st.header("Find Best Places to Travel")

    col0, col1, col2, col3 = st.columns(4)

    with col0:
        current_city = st.selectbox("Your Current City", options=ALL_PLACES)

    with col1:
        start_date = st.date_input("Start date", date.today())

    with col2:
        end_date = st.date_input("End date", date.today())

    with col3:
        travel_type = st.selectbox("Travel type", ["Solo", "Family", "Friends", "Honeymoon"])

    col4, col5 = st.columns(2)

    with col4:
        transport_mode = st.selectbox("Transport Mode", ["Car", "Bike", "Train", "Flight"])

    with col5:
        max_distance = st.slider("Max Distance (km)", min_value=50, max_value=3000, value=1000, step=50)

    if st.button("🔍 Find Best Places"):
        if start_date > end_date:
            st.error("❌ Start date must be before end date")
        else:
            with st.spinner("Analyzing weather, distance, time & festivals..."):
                df, note = recommend_travel(
                    start_date=start_date,
                    end_date=end_date,
                    travel_type=travel_type,
                    current_city=current_city,
                    transport_mode=transport_mode,
                    max_distance_km=max_distance
                )

            if df is None or df.empty:
                st.warning("⚠️ No places found within selected distance.")
            else:
                st.success("🏆 Top Travel Recommendations")
                st.info(note)

                # --------- FESTIVAL BADGE ---------
                def festival_badge(fest):
                    if fest and str(fest).strip():
                        return "🎉 Festival"
                    return "—"

                if "Festival" in df.columns:
                    df["Festival Badge"] = df["Festival"].apply(festival_badge)
                else:
                    df["Festival Badge"] = "—"

                # --------- SHOW SELECTED TRANSPORT ---------
                icon = TRANSPORT_ICONS.get(transport_mode, "")
                st.write(f"### Selected Transport: {icon} {transport_mode}")

                # --------- REORDER COLUMNS ---------
                cols = [
                    "Festival Badge",
                    "Place",
                    "Distance (km)",
                    "Travel Time",
                    "Avg Temp (°C)",
                    "Condition",
                    "Avg Rain",
                    "Festival" if "Festival" in df.columns else None,
                    "Score",
                    "Why recommended?"
                ]

                cols = [c for c in cols if c in df.columns]
                df = df[cols]

                st.dataframe(df, use_container_width=True)

# =================================================
# 🌦 WEATHER PREDICTION TAB
# =================================================
with tabs[1]:
    st.header("Weather Prediction")

    col1, col2 = st.columns(2)
    with col1:
        city = st.selectbox("City / Place", options=ALL_PLACES)
    with col2:
        selected_date = st.date_input("Select date", date.today())

    if st.button("🌤 Get Weather"):
        today = date.today()

        # ---------- PAST / TODAY ----------
        if selected_date <= today:
            actual_sql = text("""
                SELECT *
                FROM (
                    SELECT * FROM weather_master
                    UNION ALL
                    SELECT * FROM weather_data
                ) t
                WHERE name = :city
                  AND datetime = :dt
                ORDER BY fetched_at DESC
                LIMIT 1
            """)

            actual_df = pd.read_sql(actual_sql, engine, params={"city": city, "dt": selected_date})

            pred_sql = text("""
                SELECT *
                FROM weather_predictions
                WHERE name = :city
                  AND predicted_date = :dt
                LIMIT 1
            """)

            pred_df = pd.read_sql(pred_sql, engine, params={"city": city, "dt": selected_date})

            if actual_df.empty:
                st.error("❌ No actual weather data found")
            else:
                row = actual_df.iloc[0]
                st.success("✅ Actual Weather Data Found")

                actual_temp = row["temp"]

                m1, m2, m3 = st.columns(3)
                m1.metric("🌡 Actual Temp (°C)", round(actual_temp, 1))
                m2.metric("☁ Condition", row.get("conditions", "—"))
                m3.metric("🌧 Rain", "Yes" if row.get("precip", 0) > 0 else "No")

                if not pred_df.empty:
                    pred_row = pred_df.iloc[0]
                    pred_temp = pred_row["pred_temp"]
                    error = actual_temp - pred_temp

                    st.write("### 🤖 Prediction vs Actual")
                    a1, a2, a3 = st.columns(3)
                    a1.metric("🤖 Predicted (°C)", round(pred_temp, 1))
                    a2.metric("📏 Actual (°C)", round(actual_temp, 1))
                    a3.metric("❌ Error", round(error, 2))

        # ---------- FUTURE ----------
        else:
            sql = text("""
                SELECT *
                FROM weather_predictions
                WHERE name = :city
                  AND predicted_date = :dt
                LIMIT 1
            """)

            dfw = pd.read_sql(sql, engine, params={"city": city, "dt": selected_date})

            if dfw.empty:
                st.error("❌ No AI prediction found")
            else:
                row = dfw.iloc[0]
                st.success("✅ AI Weather Prediction Found")

                temp = row["pred_temp"]

                m1, m2, m3 = st.columns(3)
                m1.metric("🌡 Predicted Temp (°C)", round(temp, 1))
                m2.metric("☁ Condition", row.get("conditions", "—"))
                m3.metric("🌧 Rain", "Yes" if row.get("pred_rain_flag", 0) == 1 else "No")

st.success("✅ System Ready")
import matplotlib.pyplot as plt

# Temperature Trend (Last 7 Days)
trend_sql = text("""
    SELECT datetime, temp
    FROM weather_master
    WHERE name = :city
    ORDER BY datetime DESC
    LIMIT 7
""")

trend_df = pd.read_sql(trend_sql, engine, params={"city": city})

if not trend_df.empty:
    trend_df = trend_df.sort_values("datetime")

    fig, ax = plt.subplots()
    ax.plot(trend_df["datetime"], trend_df["temp"], marker='o')
    ax.set_title("Temperature Trend (Last 7 Days)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Temperature (°C)")
    plt.xticks(rotation=45)

    st.pyplot(fig)  