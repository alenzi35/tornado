import os
import urllib.request
import pygrib
import numpy as np
import json
import datetime
import requests
from pyproj import Proj


# ================= CONFIG =================

DATA_DIR = "data"
GRIB_PATH = "data/rap.grib2"
OUTPUT_JSON = "map/data/tornado_prob_lcc.json"

INTERCEPT = -14

COEFFS = {
    "CAPE": 2.88592370e-03,
    "CIN":  2.38728498e-05,
    "HLCY": 8.85192696e-03
}


os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs("map/data", exist_ok=True)


# ================= TIME LOGIC =================

def get_target_cycle():
    """
    We want: (current hour - 1)z F01
    Example:
      Now = 14:20 → use 13z F01 → valid 14–15
    """

    now = datetime.datetime.utcnow()

    run_time = now - datetime.timedelta(hours=1)

    date = run_time.strftime("%Y%m%d")
    hour = run_time.strftime("%H")

    return date, hour


DATE, HOUR = get_target_cycle()
FCST = "01"


# ================= URL =================

RAP_URL = (
    f"https://noaa-rap-pds.s3.amazonaws.com/"
    f"rap.{DATE}/rap.t{HOUR}z.awip32f{FCST}.grib2"
)

print("Target:", DATE, HOUR, "F01")
print("URL:", RAP_URL)


# ================= CHECK IF FILE EXISTS =================

def url_exists(url):
    r = requests.head(url)
    return r.status_code == 200


if not url_exists(RAP_URL):
    print("RAP file not ready yet. Skipping.")
    exit(0)


print("RAP file available. Processing.")


# ================= DOWNLOAD =================

urllib.request.urlretrieve(RAP_URL, GRIB_PATH)


# ================= OPEN GRIB =================

grbs = pygrib.open(GRIB_PATH)


def pick_var(grbs, shortname, typeOfLevel=None, bottom=None, top=None):

    for g in grbs:

        if g.shortName.lower() != shortname.lower():
            continue

        if typeOfLevel and g.typeOfLevel != typeOfLevel:
            continue

        if bottom is not None and top is not None:

            if not hasattr(g, "bottomLevel"):
                continue

            if not (
                abs(g.bottomLevel - bottom) < 1 and
                abs(g.topLevel - top) < 1
            ):
                continue

        return g

    raise RuntimeError(f"{shortname} not found")


# ================= LOAD DATA =================

grbs.seek(0)
cape_msg = pick_var(grbs, "cape", "surface")

grbs.seek(0)
cin_msg = pick_var(grbs, "cin", "surface")

grbs.seek(0)
hlcy_msg = pick_var(
    grbs,
    "hlcy",
    "heightAboveGroundLayer",
    0,
    1000
)


cape = cape_msg.values
cin = cin_msg.values
hlcy = hlcy_msg.values


# ================= LAT/LON =================

lats, lons = cape_msg.latlons()


# ================= PROJECTION =================

params = cape_msg.projparams

proj_lcc = Proj(
    proj="lcc",
    lat_1=params["lat_1"],
    lat_2=params["lat_2"],
    lat_0=params["lat_0"],
    lon_0=params["lon_0"],
    a=params.get("a", 6371229),
    b=params.get("b", 6371229)
)


x_vals, y_vals = proj_lcc(lons, lats)


# ================= CLEAN =================

cape = np.nan_to_num(cape)
cin = np.nan_to_num(cin)
hlcy = np.nan_to_num(hlcy)


# ================= PROB =================

linear = (
    INTERCEPT +
    COEFFS["CAPE"] * cape +
    COEFFS["CIN"] * cin +
    COEFFS["HLCY"] * hlcy
)

prob = 1 / (1 + np.exp(-linear))


# ================= FEATURES =================

features = []

rows, cols = prob.shape

for i in range(rows):
    for j in range(cols):

        x = x_vals[i, j]
        y = y_vals[i, j]

        dx = x_vals[i, j+1] - x if j < cols-1 else x - x_vals[i, j-1]
        dy = y_vals[i+1, j] - y if i < rows-1 else y - y_vals[i-1, j]

        features.append({
            "x": float(x),
            "y": float(y),
            "dx": float(abs(dx)),
            "dy": float(abs(dy)),
            "prob": float(prob[i, j])
        })


# ================= OUTPUT =================

valid_start = f"{int(HOUR):02d}:00"
valid_end = f"{(int(HOUR)+1)%24:02d}:00"

output = {
    "run_date": DATE,
    "run_hour": HOUR,
    "forecast": "F01",
    "valid": f"{valid_start}-{valid_end} UTC",
    "generated": datetime.datetime.utcnow().isoformat() + "Z",
    "projection": params,
    "features": features
}


with open(OUTPUT_JSON, "w") as f:
    json.dump(output, f)


print("Updated:", OUTPUT_JSON)

In root -> .gitignore:
data/*.grib2
data/*.idx

In root -> README.md:
# tornado-probability

In root -> index.html:
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>LCC Tornado Probability Map</title>

<style>
  body {
    margin: 0;
    overflow: hidden;
    background: #111;
  }

  canvas {
    display: block;
  }

  #tooltip {
    position: absolute;
    padding: 6px 10px;
    background: rgba(0,0,0,0.85);
    color: white;
    border-radius: 5px;
    pointer-events: none;
    display: none;
    font-family: sans-serif;
    font-size: 13px;
    white-space: nowrap;
  }

  #forecastInfo {
    position: absolute;
    top: 10px;
    left: 10px;
    padding: 8px 12px;
    background: rgba(0,0,0,0.7);
    color: white;
    font-family: sans-serif;
    font-size: 13px;
    border-radius: 6px;
    z-index: 10;
  }
</style>
</head>

<body>

<canvas id="mapCanvas"></canvas>
<div id="tooltip"></div>
<div id="forecastInfo">Loading forecast…</div>

<script>
const canvas = document.getElementById("mapCanvas");
const ctx = canvas.getContext("2d");
const tooltip = document.getElementById("tooltip");
const infoBox = document.getElementById("forecastInfo");

let scale = 1;
let offsetX = 0;
let offsetY = 0;

let dragging = false;
let lastX, lastY;

let cells = [];
let borders = [];

let minProb = Infinity;
let maxProb = -Infinity;


// --------------------------------
// Resize
// --------------------------------
function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
window.addEventListener("resize", resizeCanvas);
resizeCanvas();


// --------------------------------
// Load borders
// --------------------------------
fetch("map/data/borders_lcc.json")
  .then(r => r.json())
  .then(data => {
    borders = data.features;
    fitView();
    draw();
  });


  
// --------------------------------
// Load cells
// --------------------------------
fetch("map/data/tornado_prob_lcc.json")
  .then(r => r.json())
  .then(data => {

    cells = data.features;

    // Compute probability range
    cells.forEach(c => {
      minProb = Math.min(minProb, c.prob);
      maxProb = Math.max(maxProb, c.prob);
    });

    // -------------------------------
    // Update forecast info box
    // -------------------------------
    const runDate = data.run_date || "??????";
    const runHour = data.run_hour || "??";
    const fcst = data.forecast || "F01";
    // Compute valid forecast hour for display
    const validStart = (parseInt(runHour,10)+1)%24;
    const validEnd = (parseInt(runHour,10)+2)%24;
    function pad(n){return n.toString().padStart(2,"0");}
    infoBox.innerHTML =
      `<b>RAP Tornado Probability</b><br>
      Run: ${runDate} ${pad(runHour)}Z (${fcst})<br>
      Valid: ${pad(validStart)}:00–${pad(validEnd)}:00 UTC`;

    fitView();
    draw();
  });


// --------------------------------
// Normalize probability → 0..1
// --------------------------------
function normProb(p) {
  if (maxProb === minProb) return 0;
  return (p - minProb) / (maxProb - minProb);
}


// --------------------------------
// Probability → Color
// Blue → Purple → Red
// --------------------------------
function probToColor(p) {
  const t = normProb(p);
  let r, g, b;

  if (t < 0.5) {
    const k = t * 2;
    r = Math.floor(128 * k);
    g = 0;
    b = Math.floor(255 - 127 * k);
  } else {
    const k = (t - 0.5) * 2;
    r = Math.floor(128 + 127 * k);
    g = 0;
    b = Math.floor(128 - 128 * k);
  }

  return `rgba(${r},${g},${b},0.8)`;
}


// --------------------------------
// Fit view
// --------------------------------
function fitView() {
  let minX = Infinity, maxX = -Infinity;
  let minY = Infinity, maxY = -Infinity;

  cells.forEach(c => {
    minX = Math.min(minX, c.x);
    maxX = Math.max(maxX, c.x + (c.dx||1));
    minY = Math.min(minY, c.y);
    maxY = Math.max(maxY, c.y + (c.dy||1));
  });

  borders.forEach(line => {
    line.forEach(([x,y]) => {
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    });
  });

  const rx = maxX - minX;
  const ry = maxY - minY;

  scale = Math.min(
    canvas.width / rx,
    canvas.height / ry
  ) * 0.9;

  offsetX = canvas.width/2 - (minX + rx/2) * scale;
  offsetY = canvas.height/2 + (minY + ry/2) * scale;
}


// --------------------------------
// Draw
// --------------------------------
function draw() {

  ctx.setTransform(1,0,0,1,0,0);
  ctx.clearRect(0,0,canvas.width,canvas.height);

  ctx.setTransform(
    scale, 0,
    0, -scale,
    offsetX, offsetY
  );

  // ----- Cells -----
  cells.forEach(c => {
    ctx.fillStyle = probToColor(c.prob);
    const dx = c.dx || 1000;
    const dy = c.dy || 1000;
    ctx.fillRect(c.x, c.y, dx, dy);
  });

  // ----- Borders -----
  ctx.strokeStyle = "white";
  ctx.lineWidth = 1/scale;

  ctx.beginPath();
  borders.forEach(line => {
    line.forEach(([x,y], i) => {
      if (i === 0) ctx.moveTo(x,y);
      else ctx.lineTo(x,y);
    });
  });
  ctx.stroke();
}


// --------------------------------
// Screen → LCC
// --------------------------------
function screenToLCC(px, py) {
  return {
    x: (px - offsetX) / scale,
    y: -(py - offsetY) / scale
  };
}


// --------------------------------
// Hover tooltip
// --------------------------------
canvas.addEventListener("mousemove", e => {
  const { x, y } = screenToLCC(e.offsetX, e.offsetY);

  let hit = null;

  for (const c of cells) {
    const dx = c.dx || 1000;
    const dy = c.dy || 1000;
    if (x >= c.x && x <= c.x + dx && y >= c.y && y <= c.y + dy) {
      hit = c;
      break;
    }
  }

  if (hit) {
    tooltip.style.display = "block";
    tooltip.style.left = (e.pageX + 12) + "px";
    tooltip.style.top = (e.pageY + 12) + "px";
    tooltip.innerHTML = `Probability: ${(hit.prob * 100).toFixed(4)}%`;
  } else {
    tooltip.style.display = "none";
  }
});


// --------------------------------
// Zoom
// --------------------------------
canvas.addEventListener("wheel", e => {
  e.preventDefault();
  const z = e.deltaY < 0 ? 1.15 : 0.87;
  const mx = e.offsetX;
  const my = e.offsetY;
  offsetX = mx - z*(mx - offsetX);
  offsetY = my - z*(my - offsetY);
  scale *= z;
  draw();
});


// --------------------------------
// Pan
// --------------------------------
canvas.addEventListener("mousedown", e => {
  dragging = true;
  lastX = e.clientX;
  lastY = e.clientY;
});

window.addEventListener("mouseup", () => dragging = false);

window.addEventListener("mousemove", e => {
  if (!dragging) return;
  offsetX += e.clientX - lastX;
  offsetY += e.clientY - lastY;
  lastX = e.clientX;
  lastY = e.clientY;
  draw();
});
</script>

</body>
</html>
