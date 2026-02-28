import pandas as pd
from datetime import date, timedelta
from sqlalchemy import create_engine, text
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier

#sCONFIG
DB_URL = "mysql+pymysql://root:root@localhost:3306/weather_project"
engine = create_engine(DB_URL, future=True)

MAX_PREDICT_DAYS = 60
MIN_ROWS_CITY = 120
MIN_ROWS_PLACE = 90

FEATURES = [
    "temp_lag_1",
    "temp_lag_7",
    "humidity",
    "windspeed",
    "cloudcover",
    "uvindex",
    "month",
    "dayofyear"
]

#CONDITION LOGIC
def derive_condition(temp, rain_flag, cloudcover):
    if rain_flag == 1:
        return "Rain", "rain", "Rain expected"
    if cloudcover >= 75:
        return "Cloudy", "cloudy", "Mostly cloudy skies"
    if temp >= 32:
        return "Hot", "clear-day", "Hot weather conditions"
    if temp <= 10:
        return "Cold", "clear-night", "Cold weather conditions"
    return "Clear", "clear-day", "Clear and pleasant weather"

# CLEAN OLD PREDICTIONS
def clean_old_predictions():
    today = date.today()
    with engine.begin() as conn:
        conn.execute(
            text("""
                DELETE FROM weather_predictions
                WHERE predicted_date > :today
            """),
            {"today": today}
        )

#LOAD DATA
def load_location_data(table, location, min_rows):
    df = pd.read_sql(
        text(f"""
            SELECT
                datetime, temp, feelslike, humidity,
                windspeed, cloudcover, uvindex,
                precip, sunrise, sunset
            FROM {table}
            WHERE name = :loc
            ORDER BY datetime
        """),
        engine,
        params={"loc": location}
    )

    if len(df) < min_rows:
        return None

    df["datetime"] = pd.to_datetime(df["datetime"])
    df["rain_flag"] = (df["precip"].fillna(0) > 0).astype(int)

    df["temp_lag_1"] = df["temp"].shift(1)
    df["temp_lag_7"] = df["temp"].shift(7)
    df["month"] = df["datetime"].dt.month
    df["dayofyear"] = df["datetime"].dt.dayofyear

    df = df.dropna()
    return df

# ================= TRAIN & PREDICT =================
def train_and_predict(location, table, min_rows):
    df = load_location_data(table, location, min_rows)

    if df is None:
        print(f"Skip {location} (not enough data)")
        return

    X = df[FEATURES]
    y_temp = df["temp"]
    y_rain = df["rain_flag"]

    temp_model = RandomForestRegressor(
        n_estimators=300, random_state=42, n_jobs=-1
    )
    rain_model = RandomForestClassifier(
        n_estimators=200, random_state=42, n_jobs=-1
    )

    temp_model.fit(X, y_temp)
    rain_model.fit(X, y_rain)

    last = df.iloc[-1]
    base_date = date.today()

    current_temp = last["temp"]
    humidity = last["humidity"]
    feelslike = last["feelslike"]
    windspeed = last["windspeed"]
    cloudcover = last["cloudcover"]
    uvindex = last["uvindex"]
    sunrise = last["sunrise"]
    sunset = last["sunset"]

    print(f"Predicting for {location}")

    for day in range(1, MAX_PREDICT_DAYS + 1):
        pred_date = base_date + timedelta(days=day)

        row = {
            "temp_lag_1": current_temp,
            "temp_lag_7": df.iloc[-7]["temp"] if len(df) >= 7 else current_temp,
            "humidity": humidity,
            "windspeed": windspeed,
            "cloudcover": cloudcover,
            "uvindex": uvindex,
            "month": pred_date.month,
            "dayofyear": pred_date.timetuple().tm_yday
        }

        X_next = pd.DataFrame([row])

        pred_temp = float(temp_model.predict(X_next)[0])
        rain_prob = float(rain_model.predict_proba(X_next)[0][1])
        rain_flag = int(rain_prob >= 0.5)

        condition, icon, description = derive_condition(
            pred_temp, rain_flag, cloudcover
        )

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO weather_predictions
                    (name, base_date, predicted_date,
                     pred_temp, pred_rain_prob, pred_rain_flag,
                     humidity, feelslike, windspeed, uvindex,
                     conditions, description, icon,
                     sunrise, sunset)
                    VALUES
                    (:name, :base, :pdate,
                     :temp, :rprob, :rflag,
                     :humidity, :feelslike, :windspeed, :uvindex,
                     :conditions, :description, :icon,
                     :sunrise, :sunset)
                    ON DUPLICATE KEY UPDATE
                        pred_temp = VALUES(pred_temp),
                        pred_rain_prob = VALUES(pred_rain_prob),
                        pred_rain_flag = VALUES(pred_rain_flag),
                        conditions = VALUES(conditions),
                        description = VALUES(description),
                        icon = VALUES(icon)
                """),
                {
                    "name": location,
                    "base": base_date,
                    "pdate": pred_date,
                    "temp": round(pred_temp, 2),
                    "rprob": round(rain_prob, 3),
                    "rflag": rain_flag,
                    "humidity": humidity,
                    "feelslike": feelslike,
                    "windspeed": windspeed,
                    "uvindex": uvindex,
                    "conditions": condition,
                    "description": description,
                    "icon": icon,
                    "sunrise": sunrise,
                    "sunset": sunset
                }
            )

        current_temp = pred_temp

    print(f"Done: {location}")

# ================= MAIN =================
def main():
    print("\n Automatic Rolling 60-Day Prediction Started\n")
    #CLEAN
    print(" Removing old predictions...")
    clean_old_predictions()
    #Cities
    cities = pd.read_sql(
        "SELECT DISTINCT name FROM weather_master",
        engine
    )["name"]
    for c in cities:
        train_and_predict(c, "weather_master", MIN_ROWS_CITY)
    #Tourist Places
    places = pd.read_sql(
        "SELECT DISTINCT name FROM weather_data",
        engine
    )["name"]
    for p in places:
        train_and_predict(p, "weather_data", MIN_ROWS_PLACE)

    print("\nAll predictions refreshed for TODAY")
#ENTRY
if __name__ == "__main__":
    main()
