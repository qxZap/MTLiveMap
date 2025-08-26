const DEBUG_MODE = false; // Set to false to hide debug dots in player panel
const minX = -1280000;
const minY = -320000;
const maxX = 920000;
const maxY = 1880000;
const labelOffsetGame = 10000; // Game units for label above marker
let currentDateTime = '';

PIN_DATA = {
    'player': { color: '#b8bb28ff', radius: 8 },
    'npc': { color: '#00ff00', radius: 6 },
    'garage': { color: '#272885ff', radius: 4 },
    'police': { color: '#1539daff', radius: 8 },
    'admin': { color: '#f0540bff', radius: 8 }
}

function coordinatesToMapUnits(x, y) {
    const mapX = ((x - minX) / (maxX - minX)) * 256;
    const mapY = ((y - minY) / (maxY - minY)) * 256;
    return { x: mapX, y: mapY };
}

function getCurrentDateTime() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds} EEST`;
}

if (DEBUG_MODE) {
    currentDateTime = getCurrentDateTime();
}

// Load saved map state from localStorage, if available
const savedCenter = localStorage.getItem('mapCenter') ? JSON.parse(localStorage.getItem('mapCenter')) : [0, 0];
const savedZoom = localStorage.getItem('mapZoom') ? parseInt(localStorage.getItem('mapZoom')) : 2;

const map = L.map('map', {
    crs: L.CRS.Simple,
    worldCopyJump: false,
    minZoom: 1,
    maxZoom: 6,
    maxBounds: [[-1880000, -1280000], [320000, 920000]],
    maxBoundsViscosity: 1.0
}).setView(savedCenter, savedZoom);

// Save map center and zoom whenever they change
map.on('moveend', () => {
    const center = map.getCenter();
    localStorage.setItem('mapCenter', JSON.stringify([center.lat, center.lng]));
});

map.on('zoomend', () => {
    localStorage.setItem('mapZoom', map.getZoom());
});

L.tileLayer('file:///D:/MT/LiveMap/tiles/{z}_{x}_{y}.avif', {
    minZoom: 1,
    maxZoom: 6,
    tileSize: 256,
    noWrap: true,
    attribution: 'Custom Map Tiles',
    bounds: [[-1880000, -1280000], [320000, 920000]]
}).addTo(map);

const playerMarkers = {};
const playerLabels = {};
const debugDots = new Set();

function getLatLng(X, Y) {
    return [-Y, X];
}

function newDot(id, x, y, type) {
    if (x < minX || x > maxX || y < minY || y > maxY) {
        console.warn(`${currentDateTime} - Debug dot ${id} coordinates out of bounds: Game (${x.toFixed(2)}, ${y.toFixed(2)})`);
        return;
    }
    debugDots.add(id);
    updateDot(id, x, y, type);
    if (DEBUG_MODE) console.log(`${currentDateTime} - Created debug dot ${id}: Game (${x.toFixed(2)}, ${y.toFixed(2)})`);
}

function updateDot(id, x, y, type) {
    if (x < minX || x > maxX || y < minY || y > maxY) {
        console.warn(`${currentDateTime} - Debug dot ${id} coordinates out of bounds: Game (${x.toFixed(2)}, ${y.toFixed(2)})`);
        return;
    }
    const latLng = getLatLng(x, y);
    const isPlayerType = type === 'player';
    const markerStyle = {
        radius: isPlayerType ? 8 : 6,
        fillColor: isPlayerType ? '#ff0000' : '#0000ff',
        color: '#000000',
        weight: 1,
        opacity: 1,
        fillOpacity: 0.8
    };
    if (playerMarkers[id]) {
        playerMarkers[id].setLatLng(latLng);
        playerMarkers[id].setPopupContent(`${id} (${x.toFixed(2)}, ${y.toFixed(2)})`);
        playerMarkers[id].setStyle(markerStyle);
        playerMarkers[id].gameX = x;
        playerMarkers[id].gameY = y;
        playerMarkers[id].playerName = id;
        const labelLatLng = getLatLng(x, y - labelOffsetGame);
        playerLabels[id].setLatLng(labelLatLng);
    } else {
        playerMarkers[id] = L.circleMarker(latLng, markerStyle)
            .addTo(map)
            .bindPopup(`${id} (${x.toFixed(2)}, ${y.toFixed(2)})`);
        playerMarkers[id].gameX = x;
        playerMarkers[id].gameY = y;
        playerMarkers[id].playerName = id;
        const labelLatLng = getLatLng(x, y - labelOffsetGame);
        playerLabels[id] = L.marker(labelLatLng, {
            icon: L.divIcon({ className: 'player-label', html: id })
        }).addTo(map);
        playerMarkers[id].on('popupopen', () => { map.removeLayer(playerLabels[id]); });
        playerMarkers[id].on('popupclose', () => { playerLabels[id].addTo(map); });
    }
    debugDots.add(id);
    updatePlayerPanel(Object.keys(playerMarkers).map(name => ({
        Name: name,
        X: playerMarkers[name].gameX,
        Y: playerMarkers[name].gameY
    })));
    if (DEBUG_MODE) console.log(`${currentDateTime} - Updated debug dot ${id}: Game (${x.toFixed(2)}, ${y.toFixed(2)}) -> Leaflet (${latLng[1].toFixed(4)}, ${latLng[0].toFixed(4)})`);
}

function vehicleWikiUrl(vehicle) {
    if (!vehicle) return null;
    const formatted = vehicle.trim().replace(/\s+/g, '_');
    return `https://motortown.fandom.com/wiki/${formatted}`;
}

function updatePlayerPanel(players) {
    const list = document.getElementById('player-list');
    const searchQuery = document.getElementById('player-search')?.value.toLowerCase() || '';
    list.innerHTML = '';
    players.forEach(player => {
        if (!DEBUG_MODE && debugDots.has(player.Name)) return;
        if (searchQuery && !player.Name.toLowerCase().includes(searchQuery) && (!player.DisplayName || !player.DisplayName.toLowerCase().includes(searchQuery))) {
            return;
        }
        const li = document.createElement('li');
        li.className = 'list-group-item list-group-item-action';
        let vehicleHtml = '';
        let speedHtml = '';
        if (player.Vehicle && player.Vehicle !== 'None') {
            const url = vehicleWikiUrl(player.Vehicle);
            if (url) vehicleHtml = `<div class="player-vehicle">🚗 <a href="${url}" target="_blank">${player.Vehicle}</a></div>`;
            if (player.SpeedKMH !== undefined && player.Vehicle !== 'None') speedHtml = `<div class="player-speed">Speed: ${Math.floor(player.SpeedKMH)} km/h</div>`;
        }
        li.innerHTML = `
            <div class="player-entry">
                <div class="player-data-row">
                    <div class="player-name" style="color: ${PIN_DATA[player.PlayerType]}">${player.DisplayName || player.Name}</div>
                    ${vehicleHtml}
                </div>
                <div class="player-data-row">
                    <div class="player-coords">[${player.X.toFixed(0)}, ${player.Y.toFixed(0)}]</div>
                    ${speedHtml}
                </div>
            </div>
        `;
        li.addEventListener('click', () => {
            const marker = playerMarkers[player.Name];
            if (marker) map.setView(marker.getLatLng(), map.getZoom()); // Use current zoom level
        });
        list.appendChild(li);
    });
}
async function updatePlayerPositions() {
    try {
        if (DEBUG_MODE) currentDateTime = getCurrentDateTime();
        const response = await fetch('http://localhost:8000/playerlocations');
        const data = await response.json();
        if (DEBUG_MODE) console.log(`${currentDateTime} - API Response:`, data);
        if (data.status === 'ok' && data.players) {
            data.players.forEach(player => {
                const Name = player.Name || 'Unknown';
                const X = player.X || 0;
                const Y = player.Y || 0;
                const SpeedKMH = player.SpeedKMH || 0;
                const VehicleKey = player.VehicleKey || 'None';
                // Get PlayerType, default to 'player' if missing or invalid
                const PlayerType = ['player', 'admin', 'police'].includes(player.PlayerType) ? player.PlayerType : 'player';
                let dataMapped = coordinatesToMapUnits(X, Y);
                let gameX = dataMapped.x;
                let gameY = dataMapped.y;
                if (gameX < minX || gameX > maxX || gameY < minY || gameY > maxY) {
                    console.warn(`${currentDateTime} - Player ${Name} coordinates out of bounds: Game (${gameX.toFixed(2)}, ${gameY.toFixed(2)})`);
                    return;
                }
                const latLng = getLatLng(gameX, gameY);
                // Get marker style from PIN_DATA based on PlayerType
                const markerStyle = {
                    radius: PIN_DATA[PlayerType].radius,
                    fillColor: PIN_DATA[PlayerType].color,
                    color: '#000000', // Border color remains consistent
                    weight: 1,
                    opacity: 1,
                    fillOpacity: 0.8
                };
                if (playerMarkers[Name]) {
                    playerMarkers[Name].setLatLng(latLng);
                    playerMarkers[Name].setPopupContent(`${Name} (${gameX.toFixed(2)}, ${gameY.toFixed(2)})`);
                    playerMarkers[Name].setStyle(markerStyle);
                    playerMarkers[Name].gameX = gameX;
                    playerMarkers[Name].gameY = gameY;
                    playerMarkers[Name].playerName = Name;
                    playerMarkers[Name].speedKMH = SpeedKMH;
                    playerMarkers[Name].vehicleKey = VehicleKey;
                    playerMarkers[Name].playerType = PlayerType; // Store PlayerType
                    const labelLatLng = getLatLng(gameX, gameY - labelOffsetGame);
                    playerLabels[Name].setLatLng(labelLatLng);
                    playerLabels[Name].setIcon(L.divIcon({ className: 'player-label', html: Name }));
                } else {
                    playerMarkers[Name] = L.circleMarker(latLng, markerStyle)
                        .addTo(map)
                        .bindPopup(`${Name} (${gameX.toFixed(2)}, ${gameY.toFixed(2)})`);
                    playerMarkers[Name].gameX = gameX;
                    playerMarkers[Name].gameY = gameY;
                    playerMarkers[Name].playerName = Name;
                    playerMarkers[Name].speedKMH = SpeedKMH;
                    playerMarkers[Name].vehicleKey = VehicleKey;
                    playerMarkers[Name].playerType = PlayerType; // Store PlayerType
                    const labelLatLng = getLatLng(gameX, gameY - labelOffsetGame);
                    playerLabels[Name] = L.marker(labelLatLng, {
                        icon: L.divIcon({ className: 'player-label', html: Name })
                    }).addTo(map);
                    playerMarkers[Name].on('popupopen', () => { map.removeLayer(playerLabels[Name]); });
                    playerMarkers[Name].on('popupclose', () => { playerLabels[Name].addTo(map); });
                }
            });
            // Remove markers for players no longer in the API response (excluding debug dots)
            Object.keys(playerMarkers).forEach(name => {
                if (!debugDots.has(name) && !data.players.some(p => p.Name === name)) {
                    map.removeLayer(playerMarkers[name]);
                    map.removeLayer(playerLabels[name]);
                    delete playerMarkers[name];
                    delete playerLabels[name];
                }
            });
            // Update player panel with all current players
            const allPlayers = Object.keys(playerMarkers).map(name => ({
                Name: name,
                DisplayName: playerMarkers[name].playerName,
                Vehicle: playerMarkers[name].vehicleKey,
                X: playerMarkers[name].gameX,
                Y: playerMarkers[name].gameY,
                SpeedKMH: playerMarkers[name].speedKMH,
                PlayerType: playerMarkers[name].playerType // Include PlayerType if needed in panel
            }));
            updatePlayerPanel(allPlayers);
        } else {
            console.warn(`${currentDateTime} - No players found or invalid API response:`, data);
            updatePlayerPanel([...debugDots].map(id => ({
                Name: id,
                X: playerMarkers[id]?.gameX || 0,
                Y: playerMarkers[id]?.gameY || 0
            })));
        }
    } catch (error) {
        console.error(`${currentDateTime} - Error fetching player locations:`, error);
        updatePlayerPanel([...debugDots].map(id => ({
            Name: id,
            X: playerMarkers[id]?.gameX || 0,
            Y: playerMarkers[id]?.gameY || 0
        })));
    }
}

// Add search bar event listener
document.getElementById('player-search')?.addEventListener('input', () => {
    const allPlayers = Object.keys(playerMarkers).map(name => ({
        Name: name,
        DisplayName: playerMarkers[name].playerName,
        Vehicle: playerMarkers[name].vehicleKey,
        X: playerMarkers[name].gameX,
        Y: playerMarkers[name].gameY,
        SpeedKMH: playerMarkers[name].speedKMH
    }));
    updatePlayerPanel(allPlayers);
});

window.newDot = newDot;
window.updateDot = updateDot;

updatePlayerPositions();
setInterval(updatePlayerPositions, 400);