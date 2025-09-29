from flask import Flask, render_template_string
import requests, time, math, os
import folium
from datetime import datetime

app = Flask(__name__)

TB_URL = "http://3.91.187.172:8080"
USERNAME = "tenant@thingsboard.org"
PASSWORD = "tenant"
DEVICES = {
    "DeviceA": "8f60fa90-9bec-11f0-bb3b-79d8a63f8f5f",
    "DeviceB": "950586b0-9b7d-11f0-b5de-8f27bbc7c18b"
}

# --- ADD THESE TWO LINES ---
STATIC_DIR = os.path.join(app.root_path, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
# ---------------------------

def haversine(a, b):
    R = 6371.0
    from math import radians, sin, cos, atan2, sqrt
    lat1, lon1, lat2, lon2 = map(radians, [a["lat"], a["lon"], b["lat"], b["lon"]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 2*R*atan2(sqrt(h), sqrt(1-h))

def fetch_trail(device_id, headers, start_ts, end_ts):
    url = f"{TB_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
    params = {"keys": "lat,lon", "startTs": start_ts, "endTs": end_ts,
              "limit": 10000, "agg": "NONE", "orderBy": "ASC"}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    data = r.json()
    la, lo = data.get("lat", []), data.get("lon", [])
    n = min(len(la), len(lo))
    return [{"ts": la[i]["ts"], "lat": float(la[i]["value"]), "lon": float(lo[i]["value"])} for i in range(n)]

# --- REPLACE YOUR save_map WITH THIS VERSION ---
def save_map(trail, device_name):
    if not trail:
        return None
    m = folium.Map(location=[trail[0]["lat"], trail[0]["lon"]], zoom_start=13)
    coords = [(p["lat"], p["lon"]) for p in trail]
    folium.PolyLine(coords, color="blue", weight=3).add_to(m)
    folium.Marker(coords[0], popup="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(coords[-1], popup="End", icon=folium.Icon(color="red")).add_to(m)

    # Save to filesystem path, return URL path for iframe
    filename = f"{device_name}_map.html"
    fs_path = os.path.join(STATIC_DIR, filename)
    url_path = f"/static/{filename}"
    m.save(fs_path)
    return url_path
# ------------------------------------------------

@app.route("/")
def leaderboard():
    r = requests.post(f"{TB_URL}/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    token = r.json().get("token")
    headers = {"X-Authorization": f"Bearer {token}"}

    end_ts = int(time.time() * 1000)
    start_ts = end_ts - 24*60*60*1000

    results = []
    maps = {}
    for name, dev_id in DEVICES.items():
        trail = fetch_trail(dev_id, headers, start_ts, end_ts)
        if trail:
            total_km = sum(haversine(trail[i-1], trail[i]) for i in range(1, len(trail)))
            duration_hours = (trail[-1]["ts"] - trail[0]["ts"]) / (1000*60*60)
            avg_speed = total_km / duration_hours if duration_hours > 0 else 0
            map_path = save_map(trail, name)
        else:
            total_km, avg_speed, map_path = 0, 0, None
        results.append((name, round(total_km, 2), round(avg_speed, 2)))
        maps[name] = map_path

    sorted_devices = sorted(results, key=lambda x: x[1], reverse=True)
    total_distance = round(sum(x[1] for x in sorted_devices), 2)

    template = """
    <!doctype html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <style>
        /* --- Background like the screenshot --- */
        :root{
        --ink:#0b1220;
        --card:#0f172aE6; /* slate-900 with alpha */
        --row:#111827CC;
        --accent:#2563eb;  /* blue-600 */
        --accent2:#7c3aed; /* violet-600 */
        --muted:#cbd5e1;   /* slate-300 */
        --win:#f59e0b;     /* amber-500 */
        }
        *{box-sizing:border-box}
        body{
        margin:0;
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
        color:white;
        min-height:100vh;
        /* layered gradients for that wavy blue look */
        background:
            radial-gradient(1200px 600px at -10% -20%, #1e3a8a 0%, transparent 60%),
            radial-gradient(900px 500px at 120% 20%, #4338ca 0%, transparent 60%),
            radial-gradient(700px 500px at 50% 120%, #0ea5e9 0%, transparent 60%),
            linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
        display:flex; align-items:flex-start; justify-content:center;
        padding:40px 20px;
        }
        .wrap{width: min(900px, 100%);}

        /* TOTAL banner */
        .total-banner{
        display:flex; align-items:center; justify-content:center;
        gap:12px;
        font-weight:800; letter-spacing:.5px;
        background: linear-gradient(90deg, var(--accent), var(--accent2));
        box-shadow: 0 10px 30px #0006;
        border-radius:16px;
        padding:16px 22px;
        margin:0 0 22px;
        text-transform:uppercase;
        }
        .total-banner .icon{
        display:inline-grid; place-items:center;
        width:40px; height:40px; border-radius:999px; background:#ffffff22; font-size:22px;
        }

        /* Leaderboard card */
        .card{
        background: var(--card);
        border-radius:18px;
        box-shadow: 0 20px 50px #0008;
        padding:18px;
        backdrop-filter: blur(6px);
        }

        .row{
        display:grid;
        grid-template-columns: 64px 1fr 140px 140px; /* rank | device | distance | speed */
        gap:12px;
        align-items:center;
        background: #0b1220aa;
        border:1px solid #ffffff14;
        border-radius:12px;
        padding:12px 14px;
        margin-bottom:12px;
        }
        .row.winner{
        border-color: #f59e0b66;
        box-shadow: 0 0 0 2px #f59e0b33 inset;
        background: linear-gradient(180deg, #0b1220dd, #0b1220bb);
        }
        .rank{
        display:inline-grid; place-items:center;
        width:44px; height:44px; border-radius:10px;
        font-weight:800; font-size:18px;
        background: #0b5cff;
        background: linear-gradient(135deg, var(--accent), #1d4ed8);
        box-shadow: inset 0 -3px 10px #0006;
        }
        .device{ font-weight:700; }
        .muted{ color: var(--muted); font-weight:600; text-align:right; }

        .map{
        border-radius:14px; overflow:hidden; margin:10px 0 24px;
        border:1px solid #ffffff14; box-shadow: 0 12px 24px #0007;
        }

        @media (max-width:720px){
        .row{ grid-template-columns: 56px 1fr 88px 88px; }
        }
    </style>
    </head>
    <body>
    <div class="wrap">
        <div class="total-banner">
        <div class="icon">🏆</div>
        <div>TOTAL DISTANCE:&nbsp; {{ total_distance }} km</div>
        </div>

        <div class="card">
        {% for device, dist, speed in sorted_devices %}
            <div class="row {% if loop.first %}winner{% endif %}">
            <div class="rank">#{{ loop.index }}</div>
            <div class="device">{{ device }}</div>
            <div class="muted">{{ '%.2f'|format(dist) }} km</div>
            <div class="muted">{{ '%.2f'|format(speed) }} km/h</div>
            </div>

            {% if maps[device] %}
            <div class="map">
                <iframe src="{{ maps[device] }}" width="100%" height="320"></iframe>
            </div>
            {% endif %}
        {% endfor %}
        </div>
    </div>
    </body>
    </html>
    """

    return render_template_string(template, sorted_devices=sorted_devices, total_distance=total_distance, maps=maps)

if __name__ == "__main__":
    app.run(debug=True)