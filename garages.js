const GARAGE_PREFIX = 'garage_';
const garageMarkers = {};
const garageLabels = {};

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
        const id = `${GARAGE_PREFIX}${generateGarageId(x, y)}`;
        newDot(id, coord.x, coord.y, 'garage');
    });
}

async function fetchAndUpdateGarages() {
    try {
        const response = await fetch('http://localhost:8000/garages');
        const data = await response.json();

        if (data.status === 'ok' && data.data) {
            // Remove existing garage markers
            Object.keys(garageMarkers).forEach(id => {
                map.removeLayer(garageMarkers[id]);
                if (garageLabels[id]) map.removeLayer(garageLabels[id]);
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

// Simplified newDot
function newDot(id, x, y, type) {
    if (x < minX || x > maxX || y < minY || y > maxY) return;
    debugDots.add(id);
    updateDot(id, x, y, type);
}

// Simplified updateDot for garages
function updateDot(id, x, y, type) {
    if (x < minX || x > maxX || y < minY || y > maxY) return;
    const latLng = getLatLng(x, y);

    if (type === 'garage') {
        const markerStyle = {
            radius: PIN_DATA['garage'].radius,
            fillColor: PIN_DATA['garage'].color,
            color: '#000000',
            weight: 1,
            opacity: 1,
            fillOpacity: 0.8
        };

        if (garageMarkers[id]) {
            garageMarkers[id].setLatLng(latLng);
            garageMarkers[id].setStyle(markerStyle);
        } else {
            garageMarkers[id] = L.circleMarker(latLng, markerStyle)
                .addTo(map)
                .bindPopup(`Garage ${id}`);
            const labelLatLng = getLatLng(x, y - labelOffsetGame);
            garageLabels[id] = L.marker(labelLatLng, {
                icon: L.divIcon({ className: 'garage-label', html: id })
            }).addTo(map);
            garageMarkers[id].on('popupopen', () => { map.removeLayer(garageLabels[id]); });
            garageMarkers[id].on('popupclose', () => { garageLabels[id].addTo(map); });
        }
    }

    debugDots.add(id);
}

// Initial fetch + interval
fetchAndUpdateGarages();
setInterval(fetchAndUpdateGarages, 20000);
