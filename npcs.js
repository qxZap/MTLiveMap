const NPC_PREFIX = 'npc_';
const npcMarkers = {};
const npcLabels = {};

function createNPCDots(npcs) {
    npcs.forEach((npc, index) => {
        const id = `${NPC_PREFIX}${index}`;
        const x = npc.X;
        const y = npc.Y;
        if (x === 0 && y === 0) return; // Skip invalid coordinates

        let coord = coordinatesToMapUnits(x,y)

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
            // Clear existing NPC markers
            Object.keys(npcMarkers).forEach(id => {
                map.removeLayer(npcMarkers[id]);
                if (npcLabels[id]) map.removeLayer(npcLabels[id]);
                delete npcMarkers[id];
                delete npcLabels[id];
                debugDots.delete(id);
            });
            // Create new NPC dots
            createNPCDots(data.data);
        } else {
            console.warn(`${currentDateTime} - Invalid NPC API response:`, data);
        }
    } catch (error) {
        console.error(`${currentDateTime} - Error fetching NPC locations:`, error);
    }
}

// Initial NPC fetch
fetchAndUpdateNPCs();
// Update NPCs every 5 seconds
setInterval(fetchAndUpdateNPCs, 5000);

// Modify newDot to handle NPC type
function newDot(id, x, y, type) {
    if (x < minX || x > maxX || y < minY || y > maxY) {
        console.warn(`${currentDateTime} - ${type} dot ${id} coordinates out of bounds: Game (${x.toFixed(2)}, ${y.toFixed(2)})`);
        return;
    }
    debugDots.add(id);
    updateDot(id, x, y, type);
    if (DEBUG_MODE) console.log(`${currentDateTime} - Created ${type} dot ${id}: Game (${x.toFixed(2)}, ${y.toFixed(2)})`);
}

// Modify updateDot to handle NPC type
function updateDot(id, x, y, type) {
    if (x < minX || x > maxX || y < minY || y > maxY) {
        console.warn(`${currentDateTime} - ${type} dot ${id} coordinates out of bounds: Game (${x.toFixed(2)}, ${y.toFixed(2)})`);
        return;
    }
    const latLng = getLatLng(x, y);
    const isPlayerType = type === 'player';
    const isNPCType = type === 'npc';
    const markerStyle = {
        radius: isPlayerType ? 8 : 6,
        fillColor: isPlayerType ? '#ff0000' : (isNPCType ? '#00ff00' : '#0000ff'),
        color: '#000000',
        weight: 1,
        opacity: 1,
        fillOpacity: 0.8
    };
    let targetMarkers = isNPCType ? npcMarkers : playerMarkers;
    let targetLabels = isNPCType ? npcLabels : playerLabels;
    if (targetMarkers[id]) {
        targetMarkers[id].setLatLng(latLng);
        targetMarkers[id].setPopupContent(`${id} (${x.toFixed(2)}, ${y.toFixed(2)})`);
        targetMarkers[id].setStyle(markerStyle);
        targetMarkers[id].gameX = x;
        targetMarkers[id].gameY = y;
        targetMarkers[id].type = type;
        if (targetLabels[id]) {
            const labelLatLng = getLatLng(x, y - labelOffsetGame);
            targetLabels[id].setLatLng(labelLatLng);
        }
    } else {
        targetMarkers[id] = L.circleMarker(latLng, markerStyle)
            .addTo(map)
            .bindPopup(`${id} (${x.toFixed(2)}, ${y.toFixed(2)})`);
        targetMarkers[id].gameX = x;
        targetMarkers[id].gameY = y;
        targetMarkers[id].type = type;
        if (isNPCType || isPlayerType) {
            const labelLatLng = getLatLng(x, y - labelOffsetGame);
            targetLabels[id] = L.marker(labelLatLng, {
                icon: L.divIcon({ className: `${type}-label`, html: id })
            }).addTo(map);
            targetMarkers[id].on('popupopen', () => { map.removeLayer(targetLabels[id]); });
            targetMarkers[id].on('popupclose', () => { targetLabels[id].addTo(map); });
        }
    }
    debugDots.add(id);
    if (isPlayerType) {
        updatePlayerPanel(Object.keys(playerMarkers).map(name => ({
            Name: name,
            X: playerMarkers[name].gameX,
            Y: playerMarkers[name].gameY,
            DisplayName: playerMarkers[name].playerName,
            Vehicle: playerMarkers[name].vehicleKey,
            SpeedKMH: playerMarkers[name].speedKMH
        })));
    }
    if (DEBUG_MODE) console.log(`${currentDateTime} - Updated ${type} dot ${id}: Game (${x.toFixed(2)}, ${y.toFixed(2)}) -> Leaflet (${latLng[1].toFixed(4)}, ${latLng[0].toFixed(4)})`);
}