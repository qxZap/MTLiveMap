// Leaflet-based map (CRS.Simple) with live markers
const mapDiv = document.getElementById('map');
// Initialize a simple Leaflet map
const map = L.map('map', {
  crs: L.CRS.Simple,
  minZoom: 0,
  maxZoom: 6,
  zoomControl: true
});
// World bounds and center (adjust to your world size)
const TILE = 256;
const GRID = 16; // adjust to your grid
const WORLD_W = GRID * TILE;
const WORLD_H = GRID * TILE;
map.setView([WORLD_H / 2, WORLD_W / 2], 2);
const tileLayer = L.tileLayer('http://localhost:8001/tiles/{z}_{x}_{y}.avif', {
  tileSize: 256,
  noWrap: true,
  continuousWorld: false,
  attribution: 'Custom Map Tiles'
}).addTo(map);

const markers = new Map();
let running = true;
const startBtn = document.getElementById('startBtn');
const pauseBtn = document.getElementById('pauseBtn');
const updateTime = document.getElementById('updateTime');
const status = document.getElementById('status');
startBtn.addEventListener('click', () => { running = true; startBtn.disabled = true; pauseBtn.disabled = false; status.textContent = 'Status: running'; });
pauseBtn.addEventListener('click', () => { running = false; startBtn.disabled = false; pauseBtn.disabled = true; status.textContent = 'Status: paused'; });

async function fetchPlayers() {
  try {
    const res = await fetch('http://localhost:8000/playerlocations', { cache: 'no-store' });
    const data = await res.json();
    if (data.status === 'ok' && Array.isArray(data.players)) return data.players;
  } catch (e) {
    console.error('Error fetching players', e);
  }
  return [];
}

function worldToLatLng(x, y) {
  // Convert world coordinates into map's CRS.Simple latlng
  // Assuming top-left origin; you can adjust offsets as needed
  return [y, x];
}

async function updatePlayers() {
  if (!running) return;
  const players = await fetchPlayers();
  const seen = new Set();
  for (const p of players) {
    const { X, Y, Name, UniqueID, VehicleKey } = p;
    const latlng = worldToLatLng(X, Y);
    seen.add(UniqueID);
    if (markers.has(UniqueID)) {
      markers.get(UniqueID).setLatLng(latlng);
      markers.get(UniqueID).setPopupContent(`${Name} (X:${X.toFixed(2)} Y:${Y.toFixed(2)}) Vehicle: ${VehicleKey}`);
    } else {
      const m = L.circleMarker(latlng, {
        radius: 6,
        color: '#ff0000',
        fillColor: '#ff0000',
        fillOpacity: 0.9,
        weight: 1
      }).addTo(map).bindPopup(`${Name} (X:${X.toFixed(2)} Y:${Y.toFixed(2)}) Vehicle: ${VehicleKey}`);
      markers.set(UniqueID, m);
    }
  }
  // Remove stale markers
  for (const [id, m] of markers.entries()) {
    if (!seen.has(id)) {
      map.removeLayer(m);
      markers.delete(id);
    }
  }
  updateTime.textContent = `Last update: ${new Date().toLocaleTimeString()}`;
  status.textContent = running ? 'Status: running' : 'Status: paused';
}

updatePlayers();
setInterval(updatePlayers, 5000);
