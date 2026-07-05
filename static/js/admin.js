document.addEventListener("DOMContentLoaded", () => {
    const adminSections = document.querySelectorAll("[data-admin-content]");
    const allAdminLinks = document.querySelectorAll("[data-admin-section]");
    const sidebarLinks = document.querySelectorAll(".admin-sidebar [data-admin-section]");
    const searchInputs = document.querySelectorAll("[data-admin-search]");
    const disabledActions = document.querySelectorAll(".admin-disabled-action");

    // =============================
    // ICONOS LUCIDE
    // =============================

    function renderIcons() {
        if (window.lucide) {
            window.lucide.createIcons();
        }
    }

    renderIcons();

    // =============================
    // CAMBIO DE SECCIONES
    // =============================

    function showAdminSection(sectionName, updateHash = true) {
        if (!sectionName) return;

        const targetSection = document.querySelector(`[data-admin-content="${sectionName}"]`);

        if (!targetSection) return;

        adminSections.forEach((section) => {
            section.classList.remove("active");
        });

        targetSection.classList.add("active");

        sidebarLinks.forEach((link) => {
            link.classList.remove("active");
        });

        const activeSidebarLink = document.querySelector(
            `.admin-sidebar [data-admin-section="${sectionName}"]`
        );

        if (activeSidebarLink) {
            activeSidebarLink.classList.add("active");
        }

        if (updateHash) {
            const newHash = `#admin-${sectionName}`;

            if (window.location.hash !== newHash) {
                history.pushState(null, "", newHash);
            }
        }

        window.scrollTo({
            top: 0,
            behavior: "smooth"
        });

        renderIcons();

        if (typeof window.vinovaAdminInvalidateMaps === "function") {
            window.setTimeout(() => window.vinovaAdminInvalidateMaps(), 120);
        }
    }

    allAdminLinks.forEach((link) => {
        link.addEventListener("click", (event) => {
            const sectionName = link.dataset.adminSection;

            if (!sectionName) return;

            const targetSection = document.querySelector(
                `[data-admin-content="${sectionName}"]`
            );

            if (!targetSection) return;

            event.preventDefault();
            showAdminSection(sectionName);
        });
    });

    // =============================
    // ABRIR SECCIÓN DESDE HASH
    // =============================

    function getSectionFromHash() {
        const hash = window.location.hash.replace("#", "");

        if (!hash) return null;

        if (hash.startsWith("admin-")) {
            return hash.replace("admin-", "");
        }

        return null;
    }

    function loadInitialSection() {
        const sectionFromHash = getSectionFromHash();

        if (sectionFromHash) {
            showAdminSection(sectionFromHash, false);
            return;
        }

        const editingVehicle = document.querySelector('input[name="vehiculo_id"]');

        if (editingVehicle) {
            showAdminSection("vehiculos", false);
            return;
        }

        showAdminSection("inicio", false);
    }

    loadInitialSection();

    window.addEventListener("popstate", () => {
        const sectionFromHash = getSectionFromHash() || "inicio";
        showAdminSection(sectionFromHash, false);
    });

    // =============================
    // BUSCADORES INTERNOS
    // =============================

    function normalizeText(text) {
        return text
            .toString()
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .trim();
    }

    function filterAdminList(searchInput) {
        const listName = searchInput.dataset.adminSearch;
        const listContainer = document.querySelector(`[data-admin-list="${listName}"]`);

        if (!listContainer) return;

        const searchValue = normalizeText(searchInput.value);
        const items = listContainer.querySelectorAll("[data-admin-item]");

        items.forEach((item) => {
            const itemText = normalizeText(item.textContent);

            if (!searchValue || itemText.includes(searchValue)) {
                item.classList.remove("is-hidden");
            } else {
                item.classList.add("is-hidden");
            }
        });
    }

    searchInputs.forEach((input) => {
        input.addEventListener("input", () => {
            filterAdminList(input);
        });
    });

    // =============================
    // BUSCADOR AJAX DE CLIENTE/VEHÍCULO PARA MANTENIMIENTO
    // =============================

    function debounceMaintenance(callback, delay = 350) {
        let timeout;

        return (...args) => {
            window.clearTimeout(timeout);
            timeout = window.setTimeout(() => callback(...args), delay);
        };
    }

    function setMaintenanceMessage(resultsBox, message, type = "info") {
        const safeTypes = new Set(["info", "warning", "success", "error"]);
        const messageElement = document.createElement("div");

        messageElement.className = `maintenance-results-message ${safeTypes.has(type) ? type : "info"}`;
        messageElement.textContent = message;

        resultsBox.hidden = false;
        resultsBox.replaceChildren(messageElement);
    }

    function setMaintenanceSelectionEmpty(selectedBox) {
        selectedBox.classList.add("is-empty");
        selectedBox.textContent = "Ningún cliente/vehículo seleccionado.";
    }

    function appendMaintenanceText(parent, tagName, text) {
        const element = document.createElement(tagName);
        element.textContent = text;
        parent.appendChild(element);
        return element;
    }

    function renderMaintenanceSelection(selectedBox, result) {
        selectedBox.classList.remove("is-empty");
        selectedBox.replaceChildren();

        appendMaintenanceText(selectedBox, "strong", result.usuario_nombre || "Cliente");
        appendMaintenanceText(selectedBox, "span", result.usuario_correo || "Sin correo");
        appendMaintenanceText(
            selectedBox,
            "small",
            `${result.vehiculo || "Vehículo"} · ID vehículo: ${result.vehiculo_id || "N/D"} · Registro: ${result.usuario_vehiculo_id || "N/D"}`
        );
        appendMaintenanceText(
            selectedBox,
            "small",
            `${result.codigo_catalogo || "Sin código"} · ${result.kilometraje_referencia_visible || "0"} km de referencia`
        );
    }

    function renderMaintenanceResults(resultsBox, results, onSelect) {
        const fragment = document.createDocumentFragment();

        results.forEach((result) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "maintenance-result-item";
            button.dataset.maintenanceResultId = String(result.usuario_vehiculo_id || "");

            appendMaintenanceText(button, "strong", result.usuario_nombre || "Cliente");
            appendMaintenanceText(button, "span", result.usuario_correo || "Sin correo");
            appendMaintenanceText(
                button,
                "small",
                `${result.vehiculo || "Vehículo"} · ID vehículo: ${result.vehiculo_id || "N/D"} · Registro: ${result.usuario_vehiculo_id || "N/D"}`
            );
            appendMaintenanceText(
                button,
                "small",
                `${result.codigo_catalogo || "Sin código"} · ${result.kilometraje_referencia_visible || "0"} km`
            );

            button.addEventListener("click", () => onSelect(result));
            fragment.appendChild(button);
        });

        resultsBox.hidden = false;
        resultsBox.replaceChildren(fragment);
    }

    function initMaintenanceVehicleSearch() {
        const pickers = document.querySelectorAll("[data-maintenance-client-search]");

        pickers.forEach((picker) => {
            const searchUrl = picker.dataset.searchUrl;
            const input = picker.querySelector("[data-maintenance-search-input]");
            const hiddenInput = picker.querySelector("[data-maintenance-selected-id]");
            const resultsBox = picker.querySelector("[data-maintenance-results]");
            const selectedBox = picker.querySelector("[data-maintenance-selected]");
            const clearButton = picker.querySelector("[data-maintenance-clear]");
            const form = picker.closest("form");
            const requiredMessage = picker.dataset.requiredMessage || "Selecciona un resultado de la búsqueda antes de continuar.";

            if (!searchUrl || !input || !hiddenInput || !resultsBox || !selectedBox || !form) return;

            let controller = null;

            function clearSelection() {
                hiddenInput.value = "";
                input.value = "";
                setMaintenanceSelectionEmpty(selectedBox);
                resultsBox.hidden = true;
                resultsBox.replaceChildren();
                input.focus();
            }

            function selectResult(result) {
                hiddenInput.value = result.usuario_vehiculo_id || "";
                input.value = result.label || "";
                renderMaintenanceSelection(selectedBox, result);
                resultsBox.hidden = true;
                resultsBox.replaceChildren();

                const kmInput = form.querySelector('input[name="kilometraje_actual"]');
                if (kmInput && result.kilometraje_referencia !== undefined && (!kmInput.value || Number(kmInput.value) === 0)) {
                    kmInput.value = result.kilometraje_referencia;
                }
            }

            async function searchVehicles() {
                const query = input.value.trim();
                hiddenInput.value = "";
                setMaintenanceSelectionEmpty(selectedBox);

                if (query.length < 2) {
                    resultsBox.hidden = true;
                    resultsBox.replaceChildren();
                    return;
                }

                if (controller) controller.abort();
                controller = new AbortController();

                setMaintenanceMessage(resultsBox, "Buscando coincidencias...");

                try {
                    const response = await fetch(`${searchUrl}?q=${encodeURIComponent(query)}`, {
                        headers: { "Accept": "application/json" },
                        signal: controller.signal
                    });

                    if (!response.ok) {
                        throw new Error("Respuesta no válida del servidor");
                    }

                    const data = await response.json();
                    const results = Array.isArray(data.resultados) ? data.resultados : [];

                    if (!results.length) {
                        setMaintenanceMessage(resultsBox, "No encontré vehículos registrados con esa búsqueda.", "warning");
                        return;
                    }

                    renderMaintenanceResults(resultsBox, results, selectResult);
                } catch (error) {
                    if (error.name === "AbortError") return;
                    setMaintenanceMessage(resultsBox, "No se pudo realizar la búsqueda. Intenta nuevamente.", "warning");
                }
            }

            input.addEventListener("input", debounceMaintenance(searchVehicles));
            clearButton?.addEventListener("click", clearSelection);

            form.addEventListener("submit", (event) => {
                if (!form.contains(picker)) return;

                if (!hiddenInput.value) {
                    event.preventDefault();
                    setMaintenanceMessage(resultsBox, requiredMessage, "warning");
                    input.focus();
                }
            });
        });
    }

    initMaintenanceVehicleSearch();

    // =============================
    // ACCIONES DESHABILITADAS
    // =============================

    disabledActions.forEach((button) => {
        button.addEventListener("click", (event) => {
            event.preventDefault();
            alert("Esta función se conectará en una siguiente fase.");
        });
    });

    // =============================
    // MEJORA PARA FORMULARIO DE ARCHIVAR
    // =============================

    const archiveForms = document.querySelectorAll('form[action*="/archivar"]');

    archiveForms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            const confirmed = confirm(
                "¿Seguro que deseas eliminar este vehículo del panel principal? Se conservará en el historial interno."
            );

            if (!confirmed) {
                event.preventDefault();
            }
        });
    });

    // =============================
    // CONFIRMACIONES GENÉRICAS
    // =============================

    const confirmForms = document.querySelectorAll("[data-admin-confirm]");

    confirmForms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            const message = form.dataset.adminConfirm || "¿Confirmar esta acción?";

            if (!confirm(message)) {
                event.preventDefault();
            }
        });
    });


    // =============================
    // GENERAR CÓDIGO DE CATÁLOGO
    // =============================

    function slugCatalogPart(value) {
        return String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toUpperCase()
            .replace(/[^A-Z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "");
    }

    document.querySelectorAll("[data-generate-catalog-code]").forEach((button) => {
        button.addEventListener("click", () => {
            const form = button.closest("form");
            if (!form) return;

            const marca = slugCatalogPart(form.querySelector('[name="marca"]')?.value);
            const modelo = slugCatalogPart(form.querySelector('[name="modelo"]')?.value);
            const anio = slugCatalogPart(form.querySelector('[name="anio"]')?.value);
            const codigoInput = form.querySelector('[name="codigo_catalogo"]');

            if (!codigoInput) return;

            const partes = ["VIN", marca, modelo, anio].filter(Boolean);
            codigoInput.value = partes.join("-") || "VIN-VEHICULO";
            codigoInput.focus();
        });
    });

    // =============================
    // PREVENIR DOBLE ENVÍO EN FORMULARIOS
    // =============================

    const adminForms = document.querySelectorAll("form");

    adminForms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (event.defaultPrevented) return;

            const submitButton = form.querySelector('button[type="submit"]');

            if (!submitButton) return;

            submitButton.disabled = true;
            submitButton.classList.add("admin-mini-btn-disabled");

            const originalText = submitButton.textContent.trim();

            if (originalText) {
                submitButton.dataset.originalText = originalText;
                submitButton.textContent = "Procesando...";
            }
        });
    });

    // =============================
    // MAPA MAPTILER PARA ESTABLECIMIENTOS
    // =============================

    (function initAdminEstablishmentMap() {
        const mapElement = document.getElementById("adminEstablishmentMap");
        const latInput = document.querySelector("[data-map-lat-input]");
        const lngInput = document.querySelector("[data-map-lng-input]");
        const maptilerKey = window.VINOVA_MAPTILER_KEY || "";

        if (!mapElement || !latInput || !lngInput) return;

        if (!window.maplibregl || !maptilerKey) {
            mapElement.innerHTML = `
                <div class="admin-maptiler-fallback">
                    <strong>Mapa no configurado</strong>
                    <span>Agrega MAPTILER_KEY en el archivo .env para usar el selector de ubicación.</span>
                </div>
            `;
            return;
        }

        const defaultLat = Number(mapElement.dataset.defaultLat || "-2.170998");
        const defaultLng = Number(mapElement.dataset.defaultLng || "-79.922359");
        const styleUrl = `https://api.maptiler.com/maps/streets-v2-dark/style.json?key=${encodeURIComponent(maptilerKey)}`;

        let map = null;
        let marker = null;
        let popup = null;

        function isMapSectionVisible() {
            const section = mapElement.closest(".admin-section");
            return !section || section.classList.contains("active");
        }

        function parseCoord(input, fallback) {
            const value = Number(input.value);
            return Number.isFinite(value) ? value : fallback;
        }

        function getCurrentPosition() {
            const lat = parseCoord(latInput, defaultLat);
            const lng = parseCoord(lngInput, defaultLng);
            return [lng, lat];
        }

        function setInputs(lngLat) {
            latInput.value = Number(lngLat.lat).toFixed(6);
            lngInput.value = Number(lngLat.lng).toFixed(6);
        }

        function styleAdminMapLayers() {
            if (!map || !map.getStyle() || !Array.isArray(map.getStyle().layers)) return;

            map.getStyle().layers.forEach((layer) => {
                const id = String(layer.id || "").toLowerCase();

                try {
                    if (layer.type === "background") {
                        map.setPaintProperty(layer.id, "background-color", "#020817");
                    }

                    if (layer.type === "line") {
                        const isRoad = (
                            id.includes("road") ||
                            id.includes("street") ||
                            id.includes("transport") ||
                            id.includes("highway") ||
                            id.includes("bridge") ||
                            id.includes("tunnel") ||
                            id.includes("path")
                        );

                        const isMainRoad = (
                            id.includes("motorway") ||
                            id.includes("trunk") ||
                            id.includes("primary") ||
                            id.includes("major") ||
                            id.includes("highway")
                        );

                        if (isRoad) {
                            map.setPaintProperty(layer.id, "line-color", "#2f80ff");
                            map.setPaintProperty(layer.id, "line-opacity", [
                                "interpolate",
                                ["linear"],
                                ["zoom"],
                                8, 0.24,
                                11, 0.42,
                                14, 0.72,
                                17, 0.9
                            ]);
                            map.setPaintProperty(layer.id, "line-blur", 0.05);
                        }

                        if (isMainRoad) {
                            map.setPaintProperty(layer.id, "line-color", "#38bdf8");
                            map.setPaintProperty(layer.id, "line-opacity", 0.78);
                        }
                    }

                    if (layer.type === "fill") {
                        if (id.includes("water")) {
                            map.setPaintProperty(layer.id, "fill-color", "#031b3d");
                            map.setPaintProperty(layer.id, "fill-opacity", 0.78);
                        }

                        if (id.includes("building")) {
                            map.setPaintProperty(layer.id, "fill-color", "#071a35");
                            map.setPaintProperty(layer.id, "fill-opacity", 0.72);
                        }
                    }

                    if (layer.type === "symbol") {
                        if (id.includes("label") || id.includes("name")) {
                            map.setPaintProperty(layer.id, "text-color", "#7aa7ef");
                            map.setPaintProperty(layer.id, "text-halo-color", "#020817");
                            map.setPaintProperty(layer.id, "text-halo-width", 1);
                        }

                        if (
                            (id.includes("road") || id.includes("street") || id.includes("transport")) &&
                            (id.includes("label") || id.includes("name"))
                        ) {
                            map.setPaintProperty(layer.id, "text-color", "#93c5fd");
                        }
                    }
                } catch (error) {
                    // Algunas capas de MapTiler no aceptan todas las propiedades.
                }
            });
        }

        function forceAdminMapResize() {
            if (!map) {
                createAdminMap();
                return;
            }

            map.resize();

            window.setTimeout(() => map.resize(), 120);
            window.setTimeout(() => map.resize(), 350);
            window.setTimeout(() => map.resize(), 700);
        }

        function moveMarkerToInputs() {
            if (!map || !marker) return;

            const nextPosition = getCurrentPosition();

            marker.setLngLat(nextPosition);

            map.easeTo({
                center: nextPosition,
                zoom: Math.max(map.getZoom(), 15),
                duration: 400
            });
        }

        function createAdminMap() {
            if (map || !isMapSectionVisible()) return;

            const initialPosition = getCurrentPosition();

            map = new maplibregl.Map({
                container: mapElement,
                style: styleUrl,
                center: initialPosition,
                zoom: 15,
                pitch: 0,
                bearing: 0,
                attributionControl: true
            });

            map.addControl(
                new maplibregl.NavigationControl({
                    showCompass: false,
                    visualizePitch: false
                }),
                "bottom-right"
            );

            const markerElement = document.createElement("div");
            markerElement.className = "vinova-admin-maptiler-marker";
            markerElement.innerHTML = "<b>⌖</b>";

            marker = new maplibregl.Marker({
                element: markerElement,
                draggable: true,
                anchor: "bottom"
            })
                .setLngLat(initialPosition)
                .addTo(map);

            popup = new maplibregl.Popup({
                offset: 30,
                closeButton: false,
                className: "vinova-admin-maptiler-popup"
            }).setHTML(`
                <strong>Ubicación del establecimiento</strong>
                <span>Arrastra el marcador o haz clic en el mapa.</span>
            `);

            marker.setPopup(popup);

            marker.on("dragend", () => {
                setInputs(marker.getLngLat());
            });

            map.on("click", (event) => {
                marker.setLngLat(event.lngLat);
                setInputs(event.lngLat);
            });

            map.on("load", () => {
                styleAdminMapLayers();
                marker.togglePopup();
                forceAdminMapResize();
            });

            map.on("styledata", () => {
                styleAdminMapLayers();
            });

            map.on("error", (event) => {
                console.warn("Error cargando mapa MapTiler:", event?.error || event);
            });
        }

        latInput.addEventListener("change", moveMarkerToInputs);
        lngInput.addEventListener("change", moveMarkerToInputs);

        window.vinovaAdminInvalidateMaps = () => {
            createAdminMap();
            forceAdminMapResize();
        };

        document.querySelectorAll('[data-admin-section="establecimientos"]').forEach((link) => {
            link.addEventListener("click", () => {
                window.setTimeout(() => {
                    createAdminMap();
                    forceAdminMapResize();
                }, 240);
            });
        });

        window.addEventListener("hashchange", () => {
            if (window.location.hash === "#admin-establecimientos") {
                window.setTimeout(() => {
                    createAdminMap();
                    forceAdminMapResize();
                }, 240);
            }
        });

        window.setTimeout(() => {
            createAdminMap();
            forceAdminMapResize();
        }, 400);
    })();

});