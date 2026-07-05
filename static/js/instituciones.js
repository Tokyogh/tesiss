document.addEventListener('DOMContentLoaded', () => {
    if (window.lucide) {
        window.lucide.createIcons();
    }

    const cards = Array.from(document.querySelectorAll('[data-establishment-card]'));
    const details = Array.from(document.querySelectorAll('[data-establishment-detail]'));
    const searchInput = document.getElementById('institutionSearch');
    const typeSelect = document.getElementById('institutionTypeSelect');
    const mapContainer = document.getElementById('vinovaInstitutionsMap');
    const mapFallback = document.getElementById('vinovaInstitutionsMapFallback');

    const establishments = Array.isArray(window.VINOVA_INSTITUCIONES)
        ? window.VINOVA_INSTITUCIONES
        : [];

    const MAPTILER_KEY = window.VINOVA_MAPTILER_KEY || '';
    const MAPTILER_STYLE = `https://api.maptiler.com/maps/dataviz-dark/style.json?key=${encodeURIComponent(MAPTILER_KEY)}`;
    const DEFAULT_CENTER = [-79.922359, -2.170998];

    let map = null;
    let activePopup = null;

    const markerById = new Map();

    function toNumber(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    function getEstablishmentById(id) {
        return establishments.find(item => String(item.id) === String(id));
    }

    function getMarkerIconSvg(type) {
        const icons = {
            institucion: `
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M3 10.5 12 5l9 5.5"></path>
                    <path d="M5 10h14"></path>
                    <path d="M6 10v8"></path>
                    <path d="M10 10v8"></path>
                    <path d="M14 10v8"></path>
                    <path d="M18 10v8"></path>
                    <path d="M4 18h16"></path>
                    <path d="M3 21h18"></path>
                </svg>
            `,
            concesionario: `
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M4 20V7.5A2.5 2.5 0 0 1 6.5 5h7A2.5 2.5 0 0 1 16 7.5V20"></path>
                    <path d="M16 10h2.5A1.5 1.5 0 0 1 20 11.5V20"></path>
                    <path d="M8 9h4"></path>
                    <path d="M8 13h4"></path>
                    <path d="M7 20v-3h6v3"></path>
                    <path d="M3 20h18"></path>
                </svg>
            `,
            centro_atencion: `
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M3 14v-2a9 9 0 0 1 18 0v2"></path>
                    <path d="M21 14v3a3 3 0 0 1-3 3h-1"></path>
                    <path d="M3 14v3a3 3 0 0 0 3 3h1"></path>
                    <path d="M7 14v5"></path>
                    <path d="M17 14v5"></path>
                </svg>
            `
        };

        return icons[type] || icons.concesionario;
    }

    function createMarkerElement(type, active = false) {
        const markerType = type || 'concesionario';

        const wrapper = document.createElement('div');
        wrapper.className = 'vinova-maptiler-marker-wrapper';

        const marker = document.createElement('span');
        marker.className = [
            'vinova-maptiler-marker',
            `vinova-maptiler-marker-${markerType}`,
            active ? 'active' : ''
        ].filter(Boolean).join(' ');

        marker.innerHTML = `<i>${getMarkerIconSvg(markerType)}</i>`;
        wrapper.appendChild(marker);

        return wrapper;
    }

    function markerPopupHtml(item) {
        const safeName = escapeHtml(item.nombre || 'Establecimiento VINOVA');
        const safeAddress = escapeHtml(item.direccion || 'Dirección no registrada');
        const safeType = escapeHtml(item.tipo_label || 'VINOVA');

        return `
            <div class="vinova-map-popup">
                <strong>${safeName}</strong>
                <span>${safeType}</span>
                <small>${safeAddress}</small>
            </div>
        `;
    }

    function refreshMarkerStyles(activeId = null) {
        markerById.forEach((record, markerId) => {
            const inner = record.element.querySelector('.vinova-maptiler-marker');
            if (!inner) return;

            inner.classList.toggle('active', String(markerId) === String(activeId));
        });
    }

    function setActive(id, options = {}) {
        if (!id) return;

        const item = getEstablishmentById(id);

        cards.forEach(card => {
            card.classList.toggle('active', card.dataset.id === String(id));
        });

        details.forEach(detail => {
            detail.classList.toggle('is-hidden', detail.dataset.establishmentDetail !== String(id));
        });

        refreshMarkerStyles(id);

        const record = markerById.get(String(id));

        if (record && map) {
            if (options.fly !== false) {
                map.flyTo({
                    center: record.marker.getLngLat(),
                    zoom: Math.max(map.getZoom(), 13.8),
                    speed: 0.8,
                    curve: 1.2,
                    essential: true
                });
            }

            if (activePopup) {
                activePopup.remove();
            }

            activePopup = new maplibregl.Popup({
                offset: 34,
                closeButton: false,
                className: 'vinova-maptiler-popup'
            })
                .setLngLat(record.marker.getLngLat())
                .setHTML(markerPopupHtml(record.item))
                .addTo(map);
        } else if (item && map && activePopup) {
            activePopup.remove();
            activePopup = null;
        }

        if (window.lucide) {
            window.lucide.createIcons();
        }
    }

    function firstVisibleCard() {
        return cards.find(card => !card.hidden);
    }

    function applyFilters() {
        const query = (searchInput?.value || '').trim().toLowerCase();
        const type = (typeSelect?.value || '').trim();

        let activeStillVisible = false;
        const bounds = map && window.maplibregl ? new maplibregl.LngLatBounds() : null;
        let visibleMarkerCount = 0;

        cards.forEach(card => {
            const id = String(card.dataset.id || '');
            const matchesQuery = !query || (card.dataset.search || '').includes(query);
            const matchesType = !type || card.dataset.type === type;
            const visible = matchesQuery && matchesType;

            card.hidden = !visible;

            const record = markerById.get(id);

            if (record) {
                record.element.style.display = visible ? '' : 'none';

                if (visible && bounds) {
                    bounds.extend(record.marker.getLngLat());
                    visibleMarkerCount += 1;
                }
            }

            if (visible && card.classList.contains('active')) {
                activeStillVisible = true;
            }
        });

        if (!activeStillVisible) {
            const first = firstVisibleCard();

            if (first) {
                setActive(first.dataset.id, { fly: false });
            } else {
                cards.forEach(card => card.classList.remove('active'));
                details.forEach(detail => detail.classList.add('is-hidden'));
                refreshMarkerStyles(null);

                if (activePopup) {
                    activePopup.remove();
                    activePopup = null;
                }
            }
        }

        if (!map || !bounds || visibleMarkerCount === 0) return;

        if (visibleMarkerCount > 1) {
            map.fitBounds(bounds, {
                padding: 54,
                maxZoom: 13.7,
                duration: 500
            });
        } else {
            map.easeTo({
                center: bounds.getCenter(),
                zoom: Math.max(map.getZoom(), 13.7),
                duration: 500
            });
        }
    }

    function styleMapLayers() {
        if (!map || !map.getStyle() || !Array.isArray(map.getStyle().layers)) return;

        map.getStyle().layers.forEach(layer => {
            const id = String(layer.id || '').toLowerCase();

            try {
                if (layer.type === 'background') {
                    map.setPaintProperty(layer.id, 'background-color', '#020817');
                }

                if (layer.type === 'line') {
                    const isRoad = (
                        id.includes('road') ||
                        id.includes('street') ||
                        id.includes('transport') ||
                        id.includes('bridge') ||
                        id.includes('tunnel') ||
                        id.includes('path')
                    );

                    if (isRoad) {
                        map.setPaintProperty(layer.id, 'line-color', '#1d5fe8');
                        map.setPaintProperty(layer.id, 'line-opacity', [
                            'interpolate',
                            ['linear'],
                            ['zoom'],
                            8, 0.12,
                            11, 0.24,
                            14, 0.48,
                            17, 0.64
                        ]);
                        map.setPaintProperty(layer.id, 'line-blur', 0.25);
                    }

                    if (
                        id.includes('motorway') ||
                        id.includes('trunk') ||
                        id.includes('primary') ||
                        id.includes('major')
                    ) {
                        map.setPaintProperty(layer.id, 'line-color', '#229ad0');
                        map.setPaintProperty(layer.id, 'line-opacity', 0.58);
                    }

                    if (id.includes('admin') || id.includes('boundary')) {
                        map.setPaintProperty(layer.id, 'line-color', '#2563eb');
                        map.setPaintProperty(layer.id, 'line-opacity', 0.28);
                    }
                }

                if (layer.type === 'fill') {
                    if (id.includes('water')) {
                        map.setPaintProperty(layer.id, 'fill-color', '#031b3d');
                        map.setPaintProperty(layer.id, 'fill-opacity', 0.78);
                    }

                    if (id.includes('land') || id.includes('earth') || id.includes('park')) {
                        map.setPaintProperty(layer.id, 'fill-color', '#020817');
                        map.setPaintProperty(layer.id, 'fill-opacity', 0.98);
                    }

                    if (id.includes('building')) {
                        map.setPaintProperty(layer.id, 'fill-color', '#06152f');
                        map.setPaintProperty(layer.id, 'fill-opacity', 0.7);
                    }
                }

                if (layer.type === 'symbol') {
                    if (id.includes('label') || id.includes('name')) {
                        map.setPaintProperty(layer.id, 'text-color', '#5f7da9');
                        map.setPaintProperty(layer.id, 'text-halo-color', '#020817');
                        map.setPaintProperty(layer.id, 'text-halo-width', 1);
                    }

                    if ((id.includes('road') || id.includes('transport')) && (id.includes('label') || id.includes('name'))) {
                        map.setPaintProperty(layer.id, 'text-color', '#6da7ff');
                    }
                }
            } catch (error) {
                // Algunos estilos no aceptan todas las propiedades en todas sus capas.
            }
        });
    }

    function addMarkers() {
        if (!map) return;

        const bounds = new maplibregl.LngLatBounds();
        let markerCount = 0;

        establishments.forEach(item => {
            const lat = toNumber(item.lat);
            const lng = toNumber(item.lng);

            if (lat === null || lng === null) return;

            const element = createMarkerElement(item.tipo, false);

            const marker = new maplibregl.Marker({
                element,
                anchor: 'bottom'
            })
                .setLngLat([lng, lat])
                .addTo(map);

            element.addEventListener('click', () => {
                setActive(item.id, { fly: false });
            });

            markerById.set(String(item.id), {
                marker,
                element,
                item
            });

            bounds.extend([lng, lat]);
            markerCount += 1;
        });

        if (markerCount > 1) {
            map.fitBounds(bounds, {
                padding: 54,
                maxZoom: 13.7,
                duration: 0
            });
        } else if (markerCount === 1) {
            map.setCenter(bounds.getCenter());
            map.setZoom(13.7);
        }
    }

    function showFallback(message = 'Agrega tu MAPTILER_KEY en el archivo .env para cargar el mapa interactivo.') {
        if (!mapFallback) return;

        mapFallback.hidden = false;

        const text = mapFallback.querySelector('span');
        if (text) {
            text.textContent = message;
        }
    }

    function initMapTilerMap() {
        if (!mapContainer) return;

        if (!window.maplibregl || !MAPTILER_KEY) {
            showFallback();
            return;
        }

        map = new maplibregl.Map({
            container: mapContainer,
            style: MAPTILER_STYLE,
            center: DEFAULT_CENTER,
            zoom: 11.4,
            pitch: 0,
            bearing: 0,
            attributionControl: true
        });

        map.addControl(
            new maplibregl.NavigationControl({
                showCompass: false,
                visualizePitch: false
            }),
            'bottom-right'
        );

        map.on('load', () => {
            styleMapLayers();
            addMarkers();
            applyFilters();

            const first = firstVisibleCard();

            if (first) {
                setActive(first.dataset.id, { fly: false });
            }

            window.setTimeout(() => {
                map.resize();
            }, 250);
        });

        map.on('error', () => {
            showFallback('No se pudo cargar MapTiler. Revisa tu conexión o la MAPTILER_KEY.');
        });
    }

    cards.forEach(card => {
        card.addEventListener('click', () => {
            setActive(card.dataset.id);
        });

        card.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                setActive(card.dataset.id);
            }
        });
    });

    searchInput?.addEventListener('input', applyFilters);

    typeSelect?.addEventListener('change', () => {
        const value = typeSelect.value;
        const url = new URL(window.location.href);

        if (value) {
            url.searchParams.set('tipo', value);
        } else {
            url.searchParams.delete('tipo');
        }

        window.history.replaceState({}, '', url.toString());
        applyFilters();
    });

    document.querySelectorAll('.institution-detail-close').forEach(button => {
        button.addEventListener('click', () => {
            const panel = button.closest('[data-establishment-detail]');

            if (panel) {
                panel.classList.add('is-hidden');
            }

            cards.forEach(card => card.classList.remove('active'));
            refreshMarkerStyles(null);

            if (activePopup) {
                activePopup.remove();
                activePopup = null;
            }
        });
    });

    initMapTilerMap();
    applyFilters();

    const first = firstVisibleCard();

    if (first) {
        setActive(first.dataset.id, { fly: false });
    }
});
