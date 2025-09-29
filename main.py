import requests, time, math
import csv
from datetime import datetime
from twilio.rest import Client

TB_URL = "http://3.91.187.172:8080"
from dotenv import dotenv_values
env = dotenv_values(".env")
USERNAME = env.get("USERNAME")
PASSWORD = env.get("PASSWORD")
TWILIO_SID = env.get("TWILIO_SID")
TWILIO_AUTH = env.get("TWILIO_AUTH")
TWILIO_FROM = env.get("TWILIO_FROM")
twilio = Client(TWILIO_SID, TWILIO_AUTH)
DEVICES = {
    "DeviceA": "8f60fa90-9bec-11f0-bb3b-79d8a63f8f5f",
    "DeviceB": "950586b0-9b7d-11f0-b5de-8f27bbc7c18b"
}

def haversine(a, b):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [a["lat"], a["lon"], b["lat"], b["lon"]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2*R*math.atan2(math.sqrt(h), math.sqrt(1-h))  # km

def fetch_trail(device_id, headers, start_ts, end_ts):
    url = f"{TB_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    params = {"keys": "lat,lon", "startTs": start_ts, "endTs": end_ts, "limit": 10000, "agg": "NONE", "orderBy": "ASC"}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    data = r.json()
    la, lo = data.get("lat", []), data.get("lon", [])
    n = min(len(la), len(lo))
    return [{"ts": la[i]["ts"], "lat": float(la[i]["value"]), "lon": float(lo[i]["value"])} for i in range(n)]

def recap(trail):
    if not trail:
        return "No data."
    start, end = trail[0], trail[-1]
    total_km = sum(haversine(trail[i-1], trail[i]) for i in range(1, len(trail)))
    fmt = "%Y-%m-%d %H:%M:%S"
    return (
        f"Time span: {datetime.fromtimestamp(start['ts']/1000).strftime(fmt)} → "
        f"{datetime.fromtimestamp(end['ts']/1000).strftime(fmt)}\n"
        f"Total distance traveled: {total_km:.2f} km\n"
    ), total_km

if __name__ == "__main__":
    # login
    r = requests.post(f"{TB_URL}/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    token = r.json()["token"]
    headers = {"X-Authorization": f"Bearer {token}"}

    # last 24h
    end_ts = int(time.time() * 1000)
    start_ts = end_ts - 24*60*60*1000

    distances = {}
    for name, dev_id in DEVICES.items():
        trail = fetch_trail(dev_id, headers, start_ts, end_ts)
        print(f"=== {name} ===")
        recap_text, total_km = recap(trail)
        print(recap_text)
        distances[name] = total_km
        # Save trail to CSV
        with open(f"{name}.csv", "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=["ts", "lat", "lon"])
            writer.writeheader()
            writer.writerows(trail)

    if distances.get("DeviceB", 0) > distances.get("DeviceA", 0):
        twilio.messages.create(
            body="You lost",
            from_=TWILIO_FROM,
            to="+13104289705"
        )
