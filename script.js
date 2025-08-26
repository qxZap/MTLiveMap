const DEBUG_MODE = false;
const minX = -1280000;
const minY = -320000;
const maxX = 920000;
const maxY = 1880000;
const labelOffsetGame = 10000;
let currentDateTime = '';

// New layer groups for toggling
const playerLayer = new L.layerGroup();
const npcLayer = new L.layerGroup();
const garageLayer = new L.layerGroup();

const PIN_DATA = {
    'player': { color: '#b8bb28ff', radius: 8, prefix: '', suffix: '' },
    'npc': { color: '#00ff00', radius: 6, prefix: '🚌', suffix: '' },
    'garage': { color: '#272885ff', radius: 4, prefix: '🛠️', suffix: '' },
    'police': { color: '#1539daff', radius: 8, prefix: '⭐', suffix: '' },
    'admin': { color: '#f0540bff', radius: 8, prefix: '🔨 ', suffix: '' }
};

const playerMarkers = {};
const playerLabels = {};
const npcMarkers = {};
const npcLabels = {};
const garageMarkers = {};
const garageLabels = {};
const debugDots = new Set();


function coordinatesToMapUnits(x, y) {
    const mapX = ((x - minX) / (maxX - minX)) * 256;
    const mapY = ((y - minY) / (maxY - minY)) * 256;
    return { x: mapX, y: mapY };
}

function getCurrentDateTime() {
    const now = new Date();
    const year = String(now.getFullYear()).padStart(2, '0');
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

map.on('moveend', () => {
    const center = map.getCenter();
    localStorage.setItem('mapCenter', JSON.stringify([center.lat, center.lng]));
});

map.on('zoomend', () => {
    localStorage.setItem('mapZoom', map.getZoom());
});

const baseMaps = {
    "Game Map": L.tileLayer('file:///D:/MT/LiveMap/tiles/{z}_{x}_{y}.avif', {
        minZoom: 1,
        maxZoom: 6,
        tileSize: 256,
        noWrap: true,
        attribution: 'Custom Map Tiles',
        bounds: [[-1880000, -1280000], [320000, 920000]]
    }).addTo(map)
};

const overlayMaps = {
    "Players": playerLayer.addTo(map),
    // "NPCs": npcLayer.addTo(map),
    "Garages": garageLayer.addTo(map)
};

L.control.layers(baseMaps, overlayMaps).addTo(map);

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
    const pin = PIN_DATA[type] || PIN_DATA.player;
    const markerStyle = {
        radius: pin.radius,
        fillColor: pin.color,
        color: '#000000',
        weight: 1,
        opacity: 1,
        fillOpacity: 0.8
    };

    let targetMarkers, targetLabels, layerGroup;
    let labelText = `${pin.prefix}${id}${pin.suffix}`;

    switch (type) {
        case 'player':
        case 'admin':
        case 'police':
            targetMarkers = playerMarkers;
            targetLabels = playerLabels;
            layerGroup = playerLayer;
            break;
        case 'npc':
            targetMarkers = npcMarkers;
            targetLabels = npcLabels;
            layerGroup = npcLayer;
            break;
        case 'garage':
            targetMarkers = garageMarkers;
            targetLabels = garageLabels;
            layerGroup = garageLayer;
            break;
        default:
            return;
    }

    if (targetMarkers[id]) {
        targetMarkers[id].setLatLng(latLng);
        targetMarkers[id].setPopupContent(`${id} (${x.toFixed(2)}, ${y.toFixed(2)})`);
        targetMarkers[id].setStyle(markerStyle);
        targetMarkers[id].gameX = x;
        targetMarkers[id].gameY = y;
        if (type === 'player' || type === 'admin' || type === 'police') {
            targetMarkers[id].playerName = id;
        }

        if (targetLabels[id]) {
            const labelLatLng = getLatLng(x, y - labelOffsetGame);
            targetLabels[id].setLatLng(labelLatLng);
            targetLabels[id].setIcon(L.divIcon({ className: `${type}-label`, html: labelText }));
        }

    } else {
        targetMarkers[id] = L.circleMarker(latLng, markerStyle)
            .addTo(layerGroup)
            .bindPopup(`${id} (${x.toFixed(2)}, ${y.toFixed(2)})`);
        targetMarkers[id].gameX = x;
        targetMarkers[id].gameY = y;
        if (type === 'player' || type === 'admin' || type === 'police') {
            targetMarkers[id].playerName = id;
        }

        const labelLatLng = getLatLng(x, y - labelOffsetGame);
        targetLabels[id] = L.marker(labelLatLng, {
            icon: L.divIcon({ className: `${type}-label`, html: labelText })
        }).addTo(layerGroup);

        targetMarkers[id].on('popupopen', () => { layerGroup.removeLayer(targetLabels[id]); });
        targetMarkers[id].on('popupclose', () => { layerGroup.addLayer(targetLabels[id]); });
    }

    if (DEBUG_MODE) console.log(`${currentDateTime} - Updated ${type} dot ${id}: Game (${x.toFixed(2)}, ${y.toFixed(2)}) -> Leaflet (${latLng[1].toFixed(4)}, ${latLng[0].toFixed(4)})`);
}

function vehicleWikiUrl(vehicle) {
    if (!vehicle) return null;
    const formatted = vehicle.trim().replace(/\s+/g, '_');
    return `https://motortown.fandom.com/wiki/${formatted}`;
}

// New function to update the summary counts
function updateSummaryPanel(players) {
    const totalPlayers = players.length;
    const totalAdmins = players.filter(p => p.PlayerType === 'admin').length;
    const totalPolice = players.filter(p => p.PlayerType === 'police').length;
    
    document.getElementById('total-players').textContent = totalPlayers;
    document.getElementById('total-admins').textContent = totalAdmins;
    document.getElementById('total-police').textContent = totalPolice;
}

function updatePlayerPanel(players) {
    const list = document.getElementById('player-list');
    const searchQuery = document.getElementById('player-search')?.value.toLowerCase() || '';
    
    // Call the new function to update the summary panel
    updateSummaryPanel(players);

    // Create a new map of players to quickly look up data
    const newPlayerMap = new Map(players.map(player => [player.Name, player]));

    // Remove players that are no longer in the data
    const existingPlayerElements = list.querySelectorAll('.player-entry');
    const playersToRemove = new Set();
    existingPlayerElements.forEach(element => {
        const playerName = element.dataset.playerName;
        if (!newPlayerMap.has(playerName)) {
            playersToRemove.add(playerName);
        }
    });

    playersToRemove.forEach(name => {
        const element = list.querySelector(`[data-player-name="${name}"]`)?.parentNode;
        if (element) {
            element.remove();
        }
    });

    // Add or update player entries
    players.forEach(player => {
        if (!DEBUG_MODE && debugDots.has(player.Name)) return;

        const playerType = player.PlayerType || 'player';
        const pinData = PIN_DATA[playerType];
        const formattedName = `${pinData.prefix}${player.DisplayName || player.Name}${pinData.suffix}`;

        if (searchQuery && !formattedName.toLowerCase().includes(searchQuery)) {
            const existingLi = list.querySelector(`li[data-player-name="${player.Name}"]`);
            if (existingLi) {
                existingLi.remove();
            }
            return;
        }

        let li = list.querySelector(`li[data-player-name="${player.Name}"]`);
        if (li) {
            // Update existing element
            li.querySelector('.player-name').textContent = formattedName;
            li.querySelector('.player-name').style.color = pinData.color;
            li.querySelector('.player-coords').textContent = `[${player.X.toFixed(0)}, ${player.Y.toFixed(0)}]`;

            const vehicleHtml = player.Vehicle && player.Vehicle !== 'None' ? `<div class="player-vehicle">🚗 <a href="${vehicleWikiUrl(player.Vehicle)}" target="_blank">${player.Vehicle}</a></div>` : '';
            const speedHtml = player.SpeedKMH !== undefined && player.Vehicle !== 'None' ? `<div class="player-speed">Speed: ${Math.floor(player.SpeedKMH)} km/h</div>` : '';

            li.querySelector('.player-data-row:first-child').innerHTML = `<div class="player-name" style="color: ${pinData.color}">${formattedName}</div>${vehicleHtml}`;
            li.querySelector('.player-data-row:last-child').innerHTML = `<div class="player-coords">[${player.X.toFixed(0)}, ${player.Y.toFixed(0)}]</div>${speedHtml}`;

        } else {
            // Create and append new element
            li = document.createElement('li');
            li.className = 'list-group-item list-group-item-action';
            li.dataset.playerName = player.Name;

            let vehicleHtml = '';
            let speedHtml = '';
            if (player.Vehicle && player.Vehicle !== 'None') {
                const url = vehicleWikiUrl(player.Vehicle);
                if (url) vehicleHtml = `<div class="player-vehicle">🚗 <a href="${url}" target="_blank">${player.Vehicle}</a></div>`;
                if (player.SpeedKMH !== undefined && player.Vehicle !== 'None') speedHtml = `<div class="player-speed">Speed: ${Math.floor(player.SpeedKMH)} km/h</div>`;
            }
            li.innerHTML = `
                <div class="player-entry" data-player-name="${player.Name}">
                    <div class="player-data-row">
                        <div class="player-name" style="color: ${pinData.color}">${formattedName}</div>
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
                if (marker) map.setView(marker.getLatLng(), map.getZoom());
            });
            list.appendChild(li);
        }
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
                const PlayerType = PIN_DATA[player.PlayerType] ? player.PlayerType : 'player';
                let dataMapped = coordinatesToMapUnits(X, Y);
                let gameX = dataMapped.x;
                let gameY = dataMapped.y;
                if (gameX < minX || gameX > maxX || gameY < minY || gameY > maxY) {
                    console.warn(`${currentDateTime} - Player ${Name} coordinates out of bounds: Game (${gameX.toFixed(2)}, ${gameY.toFixed(2)})`);
                    return;
                }
                const latLng = getLatLng(gameX, gameY);
                const pin = PIN_DATA[PlayerType];
                const markerStyle = {
                    radius: pin.radius,
                    fillColor: pin.color,
                    color: '#000000',
                    weight: 1,
                    opacity: 1,
                    fillOpacity: 0.8
                };

                const formattedName = `${pin.prefix}${Name}${pin.suffix}`;

                if (playerMarkers[Name]) {
                    playerMarkers[Name].setLatLng(latLng);
                    playerMarkers[Name].setPopupContent(`${formattedName} (${gameX.toFixed(2)}, ${gameY.toFixed(2)})`);
                    playerMarkers[Name].setStyle(markerStyle);
                    playerMarkers[Name].gameX = gameX;
                    playerMarkers[Name].gameY = gameY;
                    playerMarkers[Name].playerName = Name;
                    playerMarkers[Name].speedKMH = SpeedKMH;
                    playerMarkers[Name].vehicleKey = VehicleKey;
                    playerMarkers[Name].playerType = PlayerType;
                    const labelLatLng = getLatLng(gameX, gameY - labelOffsetGame);
                    playerLabels[Name].setLatLng(labelLatLng);
                    playerLabels[Name].setIcon(L.divIcon({ className: `${PlayerType}-label`, html: formattedName }));
                } else {
                    playerMarkers[Name] = L.circleMarker(latLng, markerStyle)
                        .addTo(playerLayer)
                        .bindPopup(`${formattedName} (${gameX.toFixed(2)}, ${gameY.toFixed(2)})`);
                    playerMarkers[Name].gameX = gameX;
                    playerMarkers[Name].gameY = gameY;
                    playerMarkers[Name].playerName = Name;
                    playerMarkers[Name].speedKMH = SpeedKMH;
                    playerMarkers[Name].vehicleKey = VehicleKey;
                    playerMarkers[Name].playerType = PlayerType;
                    const labelLatLng = getLatLng(gameX, gameY - labelOffsetGame);
                    playerLabels[Name] = L.marker(labelLatLng, {
                        icon: L.divIcon({ className: `${PlayerType}-label`, html: formattedName })
                    }).addTo(playerLayer);
                    playerMarkers[Name].on('popupopen', () => { playerLayer.removeLayer(playerLabels[Name]); });
                    playerMarkers[Name].on('popupclose', () => { playerLayer.addLayer(playerLabels[Name]); });
                }
            });
            Object.keys(playerMarkers).forEach(name => {
                if (!debugDots.has(name) && !data.players.some(p => p.Name === name)) {
                    playerLayer.removeLayer(playerMarkers[name]);
                    playerLayer.removeLayer(playerLabels[name]);
                    delete playerMarkers[name];
                    delete playerLabels[name];
                }
            });
            const allPlayers = Object.keys(playerMarkers).map(name => ({
                Name: name,
                DisplayName: playerMarkers[name].playerName,
                Vehicle: playerMarkers[name].vehicleKey,
                X: playerMarkers[name].gameX,
                Y: playerMarkers[name].gameY,
                SpeedKMH: playerMarkers[name].speedKMH,
                PlayerType: playerMarkers[name].playerType
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

function createNPCDots(npcs) {
    npcs.forEach((npc, index) => {
        const id = `${index}`;
        const x = npc.X;
        const y = npc.Y;
        if (x === 0 && y === 0) return;

        let coord = coordinatesToMapUnits(x, y);
        newDot(id, coord.x, coord.y, 'npc');
    });
}

async function fetchAndUpdateNPCs() {
    try {
        if (DEBUG_MODE) currentDateTime = getCurrentDateTime();
        const response = await fetch('http://localhost:8000/npcs');
        const data = await response.json();
        if (DEBUG_MODE) console.log(`${currentDateTime} - NPC API Response:`, data);
        if (data.status === 'ok' && data.data) {
            Object.keys(npcMarkers).forEach(id => {
                npcLayer.removeLayer(npcMarkers[id]);
                if (npcLabels[id]) npcLayer.removeLayer(npcLabels[id]);
                delete npcMarkers[id];
                delete npcLabels[id];
                debugDots.delete(id);
            });
            createNPCDots(data.data);
        } else {
            console.warn(`${currentDateTime} - Invalid NPC API response:`, data);
        }
    } catch (error) {
        console.error(`${currentDateTime} - Error fetching NPC locations:`, error);
    }
}

function generateGarageId(x, y) {
    const str = `${x},${y}`;
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash = hash & hash;
    }
    return (hash >>> 0).toString(16).padStart(4, '0').slice(-4);
}

function createGarageDots(garages) {
    garages.forEach(garage => {
        const x = garage.X;
        const y = garage.Y;
        if (x === 0 && y === 0) return;
        const coord = coordinatesToMapUnits(x, y);
        const id = `${generateGarageId(x, y)}`;
        newDot(id, coord.x, coord.y, 'garage');
    });
}

async function fetchAndUpdateGarages() {
    try {
        const response = await fetch('http://localhost:8000/garages');
        const data = await response.json();

        if (data.status === 'ok' && data.data) {
            Object.keys(garageMarkers).forEach(id => {
                garageLayer.removeLayer(garageMarkers[id]);
                if (garageLabels[id]) garageLayer.removeLayer(garageLabels[id]);
                delete garageMarkers[id];
                delete garageLabels[id];
                debugDots.delete(id);
            });
            createGarageDots(data.data);
        }
    } catch (error) {
        console.error(`Error fetching garages:`, error);
    }
}

document.getElementById('player-search')?.addEventListener('input', () => {
    const allPlayers = Object.keys(playerMarkers).map(name => ({
        Name: name,
        DisplayName: playerMarkers[name].playerName,
        Vehicle: playerMarkers[name].vehicleKey,
        X: playerMarkers[name].gameX,
        Y: playerMarkers[name].gameY,
        SpeedKMH: playerMarkers[name].speedKMH,
        PlayerType: playerMarkers[name].playerType
    }));
    updatePlayerPanel(allPlayers);
});

window.newDot = newDot;
window.updateDot = updateDot;

updatePlayerPositions();
setInterval(updatePlayerPositions, 400);

// fetchAndUpdateNPCs();
// setInterval(fetchAndUpdateNPCs, 5000);

fetchAndUpdateGarages();
setInterval(fetchAndUpdateGarages, 20000);
