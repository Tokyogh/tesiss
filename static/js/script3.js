document.addEventListener("DOMContentLoaded", () => {
    initLucideIcons();
    initDropdownMenus();
    initVehiclePreviewModal();
    initFilterForm();
    initRangeFilters();
    initVehicleTypeButtons();
    initStatCards();
    initFavoriteButtons();
    initPagination();
    initClearFilters();
    initCollapsibleFilters();
    initCatalogSearch();
    initBrandSearch();
});

/* ============================= */
/* UTILIDADES SEGURAS */
/* ============================= */

function normalizeText(text) {
    return String(text || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim();
}

function debounce(callback, delay = 450) {
    let timeout;

    return (...args) => {
        window.clearTimeout(timeout);
        timeout = window.setTimeout(() => callback(...args), delay);
    };
}

function getCatalogForm() {
    return document.getElementById("catalogFiltersForm");
}

function resetPageToFirst() {
    const pageInput = document.querySelector('[name="page"][form="catalogFiltersForm"], #catalogPageInput');

    if (pageInput) {
        pageInput.value = "1";
    }
}

function submitCatalogForm({ resetPage = true } = {}) {
    const form = getCatalogForm();

    if (!form) return;

    if (resetPage) {
        resetPageToFirst();
    }

    form.requestSubmit ? form.requestSubmit() : form.submit();
}

function safeStaticPath(path) {
    const rawPath = String(path || "").trim();

    if (!rawPath) return "";

    const lowered = rawPath.toLowerCase();

    if (
        lowered.startsWith("javascript:") ||
        lowered.startsWith("data:") ||
        lowered.includes("://")
    ) {
        return "";
    }

    if (rawPath.startsWith("/static/")) {
        return rawPath;
    }

    return `/static/${rawPath.replace(/^\/+/, "")}`;
}

function formatNumber(value, locale = "en-US") {
    const number = Number(value || 0);

    if (Number.isNaN(number)) {
        return "0";
    }

    return number.toLocaleString(locale);
}

/* ============================= */
/* ICONOS LUCIDE */
/* ============================= */

function initLucideIcons() {
    if (window.lucide) {
        lucide.createIcons({
            attrs: {
                "stroke-width": 2
            }
        });
    }
}

/* ============================= */
/* DROPDOWNS NAVBAR */
/* ============================= */

function initDropdownMenus() {
    const dropdowns = document.querySelectorAll(".dropdown");

    dropdowns.forEach((dropdown) => {
        const trigger = dropdown.querySelector("a");
        const menu = dropdown.querySelector(".dropdown-menu");

        if (!trigger || !menu) return;

        let timeout;

        dropdown.addEventListener("mouseenter", () => {
            clearTimeout(timeout);
            closeAllDropdowns(menu);
            menu.classList.add("show");
        });

        dropdown.addEventListener("mouseleave", () => {
            timeout = setTimeout(() => {
                menu.classList.remove("show");
            }, 220);
        });

        trigger.addEventListener("click", (event) => {
            if (trigger.getAttribute("href") === "#") {
                event.preventDefault();
                event.stopPropagation();

                const isOpen = menu.classList.contains("show");
                closeAllDropdowns(menu);

                if (!isOpen) {
                    menu.classList.add("show");
                }
            }
        });

        menu.addEventListener("click", (event) => {
            event.stopPropagation();
        });
    });

    document.addEventListener("click", () => {
        closeAllDropdowns();
    });
}

function closeAllDropdowns(exceptionMenu = null) {
    document.querySelectorAll(".dropdown-menu.show").forEach((menu) => {
        if (menu !== exceptionMenu) {
            menu.classList.remove("show");
        }
    });
}

/* ============================= */
/* FORMULARIO DE FILTROS */
/* ============================= */

function initFilterForm() {
    const form = getCatalogForm();

    if (!form) return;

    const autoSubmitControls = document.querySelectorAll(
        '#catalogFiltersForm [data-auto-submit="true"], [form="catalogFiltersForm"][data-auto-submit="true"]'
    );

    autoSubmitControls.forEach((control) => {
        const eventName = control.matches('input[type="text"], input[type="search"]') ? "input" : "change";
        const handler = eventName === "input"
            ? debounce(() => submitCatalogForm(), 520)
            : () => submitCatalogForm();

        control.addEventListener(eventName, () => {
            if (control.matches('input[type="search"], input[type="text"]')) {
                const value = control.value.trim();

                if (value.length === 1) return;
            }

            handler();
        });
    });

    form.addEventListener("submit", () => {
        cleanEmptyCatalogFields(form);
    });
}

function cleanEmptyCatalogFields(form) {
    const fields = document.querySelectorAll('input[form="catalogFiltersForm"], select[form="catalogFiltersForm"], #catalogFiltersForm input, #catalogFiltersForm select');

    fields.forEach((field) => {
        if (!field.name) return;

        if ((field.type === "checkbox" || field.type === "radio") && !field.checked) {
            field.disabled = true;
            return;
        }

        if (String(field.value || "").trim() === "") {
            field.disabled = true;
        }
    });
}

/* ============================= */
/* RANGOS FUNCIONALES */
/* ============================= */

function initRangeFilters() {
    document.querySelectorAll("[data-range-group]").forEach((group) => {
        const minNumber = group.querySelector("[data-range-number-min]");
        const maxNumber = group.querySelector("[data-range-number-max]");
        const minRange = group.querySelector("[data-range-slider-min]");
        const maxRange = group.querySelector("[data-range-slider-max]");
        const fill = group.querySelector(".catalog-range-fill");
        const text = group.querySelector("[data-range-text]");
        const prefix = group.dataset.rangePrefix || "";
        const suffix = group.dataset.rangeSuffix || "";

        if (!minNumber || !maxNumber || !minRange || !maxRange || !fill) return;

        function clampValues(source) {
            let minValue = Number(minNumber.value || minNumber.min || 0);
            let maxValue = Number(maxNumber.value || maxNumber.max || 0);
            const absoluteMin = Number(minRange.min || minNumber.min || 0);
            const absoluteMax = Number(maxRange.max || maxNumber.max || 0);

            if (Number.isNaN(minValue)) minValue = absoluteMin;
            if (Number.isNaN(maxValue)) maxValue = absoluteMax;

            minValue = Math.max(absoluteMin, Math.min(minValue, absoluteMax));
            maxValue = Math.max(absoluteMin, Math.min(maxValue, absoluteMax));

            if (minValue > maxValue) {
                if (source === "min") {
                    maxValue = minValue;
                } else {
                    minValue = maxValue;
                }
            }

            minNumber.value = String(minValue);
            maxNumber.value = String(maxValue);
            minRange.value = String(minValue);
            maxRange.value = String(maxValue);

            const left = absoluteMax === absoluteMin
                ? 0
                : ((minValue - absoluteMin) / (absoluteMax - absoluteMin)) * 100;
            const right = absoluteMax === absoluteMin
                ? 100
                : ((maxValue - absoluteMin) / (absoluteMax - absoluteMin)) * 100;

            fill.style.setProperty("--range-left", `${left}%`);
            fill.style.setProperty("--range-right", `${right}%`);

            if (text) {
                text.textContent = `${prefix}${formatNumber(minValue)} – ${prefix}${formatNumber(maxValue)}${suffix}`;
            }
        }

        minRange.addEventListener("input", () => {
            minNumber.value = minRange.value;
            clampValues("min");
        });

        maxRange.addEventListener("input", () => {
            maxNumber.value = maxRange.value;
            clampValues("max");
        });

        minNumber.addEventListener("input", () => clampValues("min"));
        maxNumber.addEventListener("input", () => clampValues("max"));

        [minRange, maxRange, minNumber, maxNumber].forEach((control) => {
            control.addEventListener("change", () => submitCatalogForm());
        });

        clampValues();
    });
}

/* ============================= */
/* TARJETAS DE TIPO */
/* ============================= */

function initVehicleTypeButtons() {
    const typeCards = document.querySelectorAll(".catalog-type-card");

    typeCards.forEach((card) => {
        const input = card.querySelector('input[type="checkbox"]');

        if (!input) return;

        card.classList.toggle("is-selected", input.checked);

        card.addEventListener("click", (event) => {
            event.preventDefault();
            input.checked = !input.checked;
            card.classList.toggle("is-selected", input.checked);
            submitCatalogForm();
        });
    });
}

/* ============================= */
/* TARJETAS DE RESUMEN */
/* ============================= */

function getCsvValues(value) {
    return String(value || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function initStatCards() {
    const statCards = document.querySelectorAll(".catalog-stat-card[data-filter-field], .catalog-stat-card[data-clear-filter-fields]");

    statCards.forEach((card) => {
        card.addEventListener("click", () => {
            const url = new URL(window.location.href);
            url.searchParams.delete("page");

            const clearFields = getCsvValues(card.dataset.clearFilterFields);

            if (clearFields.length) {
                clearFields.forEach((fieldName) => url.searchParams.delete(fieldName));
                window.location.href = url.toString();
                return;
            }

            const field = card.dataset.filterField;
            const valuesToToggle = getCsvValues(card.dataset.filterValues || card.dataset.filterValue);

            if (!field || !valuesToToggle.length) {
                window.location.href = url.toString();
                return;
            }

            const exclusiveFields = getCsvValues(card.dataset.exclusiveFields);
            const currentValues = url.searchParams.getAll(field);
            const alreadyActive = valuesToToggle.every((value) => currentValues.includes(value));

            if (exclusiveFields.length) {
                exclusiveFields.forEach((fieldName) => url.searchParams.delete(fieldName));
            } else {
                url.searchParams.delete(field);
                currentValues
                    .filter((value) => !valuesToToggle.includes(value))
                    .forEach((value) => url.searchParams.append(field, value));
            }

            if (!alreadyActive) {
                valuesToToggle.forEach((value) => url.searchParams.append(field, value));
            }

            window.location.href = url.toString();
        });
    });
}

/* ============================= */
/* FAVORITOS VISUALES */
/* ============================= */

function initFavoriteButtons() {
    const favoriteButtons = document.querySelectorAll(".favorite-btn");

    favoriteButtons.forEach((button) => {
        button.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();

            button.classList.toggle("active");

            const icon = button.querySelector("svg");
            if (!icon) return;

            icon.setAttribute(
                "fill",
                button.classList.contains("active") ? "currentColor" : "none"
            );
        });
    });
}

/* ============================= */
/* PAGINACIÓN */
/* ============================= */

function initPagination() {
    const paginationButtons = document.querySelectorAll("[data-catalog-page]");

    paginationButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const page = Number(button.dataset.catalogPage || 1);

            if (!page || button.disabled) return;

            const url = new URL(window.location.href);
            url.searchParams.set("page", String(page));
            window.location.href = url.toString();
        });
    });
}

/* ============================= */
/* LIMPIAR FILTROS */
/* ============================= */

function initClearFilters() {
    const clearButton = document.querySelector(".clear-filters");

    if (!clearButton) return;

    clearButton.addEventListener("click", () => {
        window.location.href = window.location.pathname;
    });
}

/* ============================= */
/* FILTROS COLAPSABLES */
/* ============================= */

function initCollapsibleFilters() {
    const sections = document.querySelectorAll(".catalog-filter-section");

    sections.forEach((section) => {
        const titleButton = section.querySelector(".catalog-filter-title");

        if (!titleButton) return;

        const hasCollapsibleContent =
            section.querySelector(".catalog-checkbox-list") ||
            section.querySelector(".catalog-filter-search") ||
            section.querySelector(".catalog-range-control") ||
            section.querySelector(".catalog-year-filter") ||
            section.querySelector(".catalog-type-grid") ||
            section.querySelector(".catalog-number-grid");

        if (!hasCollapsibleContent) return;

        titleButton.addEventListener("click", () => {
            section.classList.toggle("is-collapsed");
        });
    });
}

/* ============================= */
/* BUSCADOR PRINCIPAL */
/* ============================= */

function initCatalogSearch() {
    const searchInput = document.querySelector(".catalog-main-search input");
    const vehicleCards = document.querySelectorAll(".catalog-vehicle-card");

    if (!searchInput) return;

    searchInput.addEventListener("input", debounce(() => {
        const searchValue = normalizeText(searchInput.value);

        if (searchValue.length >= 2 || searchValue.length === 0) {
            submitCatalogForm();
            return;
        }

        vehicleCards.forEach((card) => {
            const cardText = normalizeText(card.textContent || "");
            card.dataset.hiddenBySearch = cardText.includes(searchValue) ? "false" : "true";
        });
    }, 620));
}

/* ============================= */
/* BUSCADOR DE MARCAS */
/* ============================= */

function initBrandSearch() {
    const brandSearchInput = document.querySelector(".catalog-filter-search input[data-local-filter='brands']");

    if (!brandSearchInput) return;

    const brandSection = brandSearchInput.closest(".catalog-filter-section");

    if (!brandSection) return;

    const brandRows = brandSection.querySelectorAll(".catalog-checkbox-row");

    brandSearchInput.addEventListener("input", () => {
        const searchValue = normalizeText(brandSearchInput.value);

        brandRows.forEach((row) => {
            const rowText = normalizeText(row.textContent);
            row.style.display = rowText.includes(searchValue) ? "" : "none";
        });
    });
}

/* ============================= */
/* MODAL DE PREVISUALIZACIÓN */
/* ============================= */

function initVehiclePreviewModal() {
    const modal = document.getElementById("vehiclePreviewModal");
    const previewButtons = document.querySelectorAll(".catalog-preview-btn");

    if (!modal || previewButtons.length === 0) return;

    const tabButtons = modal.querySelectorAll("[data-preview-tab]");
    const body = modal.querySelector(".vehicle-preview-body");
    const systemButtons = modal.querySelectorAll("[data-system]");
    const modelViewer = document.getElementById("vinovaPreviewModel");
    const resetCameraButton = document.getElementById("resetVehicleCamera");
    const modelStatus = document.getElementById("demoModelStatus");

    const previewImage = document.getElementById("previewImage");
    const previewCode = document.getElementById("previewCode");
    const previewTitle = document.getElementById("previewTitle");
    const vehiclePreviewTitle = document.getElementById("vehiclePreviewTitle");
    const previewPrice = document.getElementById("previewPrice");
    const previewType = document.getElementById("previewType");
    const previewFuel = document.getElementById("previewFuel");
    const previewTransmission = document.getElementById("previewTransmission");
    const previewMileage = document.getElementById("previewMileage");
    const previewDescription = document.getElementById("previewDescription");
    const previewState = document.getElementById("previewState");
    const previewStateText = document.getElementById("previewStateText");
    const previewModelText = document.getElementById("previewModelText");
    const previewModelShort = document.getElementById("previewModelShort");
    const previewRegisterLink = document.getElementById("previewRegisterLink");

    const systemIcon = document.getElementById("previewSystemIcon");
    const systemName = document.getElementById("previewSystemName");
    const systemSpec = document.getElementById("previewSystemSpec");
    const systemDescription = document.getElementById("previewSystemDescription");
    const systemLocation = document.getElementById("previewSystemLocation");
    const systemPrices = document.getElementById("previewSystemPrices");

    const catalogConfig = window.VINOVA_CATALOG_CONFIG || {};
    const canEditPreview = Boolean(catalogConfig.canEditPreview);
    const editButton = document.getElementById("editPreviewSystemBtn");
    const saveButton = document.getElementById("savePreviewSystemBtn");
    const cancelButton = document.getElementById("cancelPreviewSystemBtn");
    const editPanel = document.getElementById("previewEditPanel");
    const editMessage = document.getElementById("previewEditMessage");
    const editGeneralDescription = document.getElementById("previewEditGeneralDescription");
    const editName = document.getElementById("previewEditName");
    const editSpec = document.getElementById("previewEditSpec");
    const editDescription = document.getElementById("previewEditDescription");
    const editLocation = document.getElementById("previewEditLocation");
    const editPrices = document.getElementById("previewEditPrices");

    const defaultSystems = {
        motor: {
            icon: "settings",
            name: "Sistema de motor",
            spec: "Información pendiente de configurar.",
            description: "Completa esta descripción desde el panel admin o trabajador.",
            location: "Compartimiento frontal del vehículo.",
            prices: []
        },
        transmision: {
            icon: "git-branch",
            name: "Sistema de transmisión",
            spec: "Información pendiente de configurar.",
            description: "Completa esta descripción desde el panel admin o trabajador.",
            location: "Zona inferior central del vehículo.",
            prices: []
        },
        frenos: {
            icon: "disc-3",
            name: "Sistema de frenos",
            spec: "Información pendiente de configurar.",
            description: "Completa esta descripción desde el panel admin o trabajador.",
            location: "Ruedas delanteras y traseras.",
            prices: []
        },
        suspension: {
            icon: "activity",
            name: "Sistema de suspensión",
            spec: "Información pendiente de configurar.",
            description: "Completa esta descripción desde el panel admin o trabajador.",
            location: "Conjunto de ruedas, ejes y bastidor inferior.",
            prices: []
        },
        direccion: {
            icon: "circle-dot",
            name: "Sistema de dirección",
            spec: "Información pendiente de configurar.",
            description: "Completa esta descripción desde el panel admin o trabajador.",
            location: "Columna de dirección y tren delantero.",
            prices: []
        },
        electrico: {
            icon: "zap",
            name: "Sistema eléctrico",
            spec: "Información pendiente de configurar.",
            description: "Completa esta descripción desde el panel admin o trabajador.",
            location: "Distribuido en todo el vehículo.",
            prices: []
        },
        carroceria: {
            icon: "car-front",
            name: "Sistema de carrocería",
            spec: "Información pendiente de configurar.",
            description: "Completa esta descripción desde el panel admin o trabajador.",
            location: "Estructura exterior e interior del vehículo.",
            prices: []
        }
    };

    let activeSystems = { ...defaultSystems };
    let activeSystemKey = "motor";
    let activePreviewButton = null;
    let activeSaveUrl = "";
    let currentVehicleDescription = "";
    let modelSrc = "";
    let modelLoadStarted = false;
    let modelLoaded = false;
    let editingPreview = false;

    function renderIcons() {
        initLucideIcons();
    }

    function escapeHTML(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function normalizePriceRows(rows) {
        if (!Array.isArray(rows)) return [];

        return rows
            .map((row) => {
                if (Array.isArray(row)) return [row[0] || "Repuesto", row[1] || "Consultar"];
                if (row && typeof row === "object") return [row.part || row.nombre || "Repuesto", row.price || row.precio || "Consultar"];
                return null;
            })
            .filter(Boolean);
    }

    function parseSystems(raw) {
        const merged = JSON.parse(JSON.stringify(defaultSystems));

        if (!raw) return merged;

        try {
            const parsed = JSON.parse(raw);

            if (Array.isArray(parsed)) {
                parsed.forEach((item) => {
                    if (!item || typeof item !== "object") return;
                    const key = normalizeText(item.key || item.id || item.system || item.sistema || "");
                    if (!key || !merged[key]) return;
                    merged[key] = { ...merged[key], ...item, prices: normalizePriceRows(item.prices || item.precios || item.repuestos) };
                });
                return merged;
            }

            if (parsed && typeof parsed === "object") {
                Object.keys(parsed).forEach((key) => {
                    const normalizedKey = normalizeText(key);
                    if (!merged[normalizedKey] || !parsed[key] || typeof parsed[key] !== "object") return;
                    const item = parsed[key];
                    merged[normalizedKey] = {
                        ...merged[normalizedKey],
                        ...item,
                        prices: normalizePriceRows(item.prices || item.precios || item.repuestos)
                    };
                });
            }
        } catch (error) {
            console.warn("JSON de preview 3D inválido:", error);
        }

        return merged;
    }

    function setModelStatus(state, message = "") {
        if (!modelStatus) return;

        modelStatus.classList.remove("is-loading", "is-loaded", "is-hidden", "has-error");

        if (state === "empty") {
            modelStatus.innerHTML = `
                <i data-lucide="box"></i>
                <strong>Modelo 3D pendiente</strong>
                <p>${message || "Este vehículo todavía no tiene un archivo GLB/GLTF asignado."}</p>
            `;
        }

        if (state === "loading") {
            modelStatus.classList.add("is-loading");
            modelStatus.innerHTML = `
                <i data-lucide="loader"></i>
                <strong>Cargando modelo 3D</strong>
                <p>${message || "Estamos preparando el archivo 3D del vehículo seleccionado."}</p>
            `;
        }

        if (state === "loaded") {
            modelStatus.classList.add("is-loaded", "is-hidden");
        }

        if (state === "error") {
            modelStatus.classList.add("has-error");
            modelStatus.innerHTML = `
                <i data-lucide="triangle-alert"></i>
                <strong>No se pudo cargar el modelo</strong>
                <p>${message || "Verifica que el archivo exista dentro de static/models/vehicles/."}</p>
            `;
        }

        renderIcons();
    }

    function ensureModelLoading() {
        if (!modelViewer || modelLoadStarted || !modelSrc) return;

        modelLoadStarted = true;
        modelLoaded = false;
        setModelStatus("loading");

        window.setTimeout(() => {
            modelViewer.setAttribute("src", modelSrc);
        }, 200);
    }

    function changeTab(tabName) {
        tabButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.previewTab === tabName);
        });

        if (body) {
            body.dataset.previewCurrentTab = tabName;
        }

        if (tabName === "model") {
            ensureModelLoading();
        }
    }

    function getSystemData(systemKey = activeSystemKey) {
        return activeSystems[systemKey] || activeSystems.motor || defaultSystems.motor;
    }

    function pricesToTextarea(prices) {
        return normalizePriceRows(prices)
            .map(([part, price]) => `${part} | ${price}`)
            .join("\n");
    }

    function textareaToPrices(value) {
        return String(value || "")
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean)
            .map((line) => {
                const parts = line.split("|");
                const part = (parts.shift() || "Repuesto").trim();
                const price = (parts.join("|") || "Consultar").trim();
                return [part || "Repuesto", price || "Consultar"];
            });
    }

    function fillEditForm() {
        if (!canEditPreview || !editPanel) return;

        const data = getSystemData();

        if (editGeneralDescription) editGeneralDescription.value = currentVehicleDescription || "";
        if (editName) editName.value = data.name || data.nombre || "";
        if (editSpec) editSpec.value = data.spec || data.especificacion || "";
        if (editDescription) editDescription.value = data.description || data.descripcion || "";
        if (editLocation) editLocation.value = data.location || data.ubicacion || "";
        if (editPrices) editPrices.value = pricesToTextarea(data.prices || data.precios || data.repuestos || []);
    }

    function setEditMode(enabled, message = "") {
        editingPreview = Boolean(enabled && canEditPreview);

        if (editPanel) editPanel.hidden = !editingPreview;
        if (editButton) editButton.hidden = editingPreview;
        if (saveButton) saveButton.hidden = !editingPreview;
        if (cancelButton) cancelButton.hidden = !editingPreview;
        if (editMessage) {
            editMessage.textContent = message;
            editMessage.classList.remove("is-error", "is-success");
        }

        if (editingPreview) {
            fillEditForm();
        }

        renderIcons();
    }

    function selectSystem(systemKey) {
        activeSystemKey = systemKey || "motor";
        const data = getSystemData(activeSystemKey);
        const prices = normalizePriceRows(data.prices || data.precios || data.repuestos);

        systemButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.system === activeSystemKey);
        });

        if (systemIcon) systemIcon.setAttribute("data-lucide", data.icon || "settings");
        if (systemName) systemName.textContent = data.name || data.nombre || "Sistema seleccionado";
        if (systemSpec) systemSpec.textContent = data.spec || data.especificacion || "Información pendiente de configurar.";
        if (systemDescription) systemDescription.textContent = data.description || data.descripcion || "Completa esta descripción desde admin o trabajador.";
        if (systemLocation) systemLocation.textContent = data.location || data.ubicacion || "N/D";

        if (systemPrices) {
            systemPrices.innerHTML = prices.length
                ? prices.map(([part, price]) => `<li><span>${escapeHTML(part)}</span><strong>${escapeHTML(price)}</strong></li>`).join("")
                : '<li><span>Repuestos</span><strong>Consultar</strong></li>';
        }

        if (editingPreview) {
            fillEditForm();
        }

        renderIcons();
    }

    function collectSystemsForSave() {
        const output = {};

        Object.keys(activeSystems).forEach((key) => {
            const data = activeSystems[key] || {};
            output[key] = {
                icon: data.icon || defaultSystems[key]?.icon || "settings",
                name: data.name || data.nombre || defaultSystems[key]?.name || key,
                spec: data.spec || data.especificacion || "",
                description: data.description || data.descripcion || "",
                location: data.location || data.ubicacion || "",
                prices: normalizePriceRows(data.prices || data.precios || data.repuestos || [])
            };
        });

        return output;
    }

    async function savePreviewEdits() {
        if (!canEditPreview || !activeSaveUrl) return;

        const current = getSystemData();
        activeSystems[activeSystemKey] = {
            ...current,
            icon: current.icon || defaultSystems[activeSystemKey]?.icon || "settings",
            name: editName ? editName.value.trim() : current.name,
            spec: editSpec ? editSpec.value.trim() : current.spec,
            description: editDescription ? editDescription.value.trim() : current.description,
            location: editLocation ? editLocation.value.trim() : current.location,
            prices: editPrices ? textareaToPrices(editPrices.value) : normalizePriceRows(current.prices)
        };

        currentVehicleDescription = editGeneralDescription ? editGeneralDescription.value.trim() : currentVehicleDescription;

        if (saveButton) {
            saveButton.disabled = true;
            saveButton.innerHTML = '<i data-lucide="loader"></i> Guardando...';
        }

        if (editMessage) {
            editMessage.textContent = "Guardando cambios...";
            editMessage.classList.remove("is-error", "is-success");
        }

        renderIcons();

        try {
            const response = await fetch(activeSaveUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": catalogConfig.csrfToken || ""
                },
                body: JSON.stringify({
                    descripcion: currentVehicleDescription,
                    preview_sistemas_json: JSON.stringify(collectSystemsForSave())
                })
            });

            let payload = {};
            try {
                payload = await response.json();
            } catch (error) {
                payload = {};
            }

            if (!response.ok || payload.ok === false) {
                throw new Error(payload.message || "No se pudo guardar la información.");
            }

            const compactSystems = payload.preview_sistemas_json || JSON.stringify(collectSystemsForSave());
            const savedDescription = payload.descripcion || currentVehicleDescription;

            currentVehicleDescription = savedDescription;
            activeSystems = parseSystems(compactSystems);

            if (activePreviewButton) {
                activePreviewButton.dataset.previewSystems = compactSystems;
                activePreviewButton.dataset.descripcion = savedDescription;
            }

            if (previewDescription) previewDescription.textContent = savedDescription || "Sin descripción disponible.";
            selectSystem(activeSystemKey);
            setEditMode(false);

            if (editMessage) {
                editMessage.textContent = payload.message || "Información actualizada.";
                editMessage.classList.add("is-success");
            }
        } catch (error) {
            if (editMessage) {
                editMessage.textContent = error.message || "No se pudo guardar la información.";
                editMessage.classList.add("is-error");
            }
        } finally {
            if (saveButton) {
                saveButton.disabled = false;
                saveButton.innerHTML = '<i data-lucide="save"></i> Guardar';
            }

            renderIcons();
        }
    }

    function openModal(button) {
        const codigo = button.dataset.codigo || "VINOVA";
        const marca = button.dataset.marca || "";
        const modelo = button.dataset.modelo || "";
        const anio = button.dataset.anio || "";
        const tipo = button.dataset.tipo || "N/D";
        const combustible = button.dataset.combustible || "N/D";
        const transmision = button.dataset.transmision || "N/D";
        const kilometraje = button.dataset.kilometraje || "0";
        const precio = button.dataset.precio || "0";
        const imagen = safeStaticPath(button.dataset.imagen || "");
        const estado = button.dataset.estado || "Disponible";
        const descripcion = button.dataset.descripcion || "";
        activePreviewButton = button;
        activeSaveUrl = button.dataset.saveUrl || "";
        currentVehicleDescription = descripcion;
        const modelo3dId = button.dataset.modelo3dId || "";
        const modelo3dPath = safeStaticPath(button.dataset.modelo3d || "");
        const title = `${marca} ${modelo} ${anio}`.trim() || "Vehículo VINOVA";

        activeSystems = parseSystems(button.dataset.previewSystems || "");
        modelSrc = modelo3dPath;
        modelLoadStarted = false;
        modelLoaded = false;

        if (modelViewer) {
            modelViewer.removeAttribute("src");
            modelViewer.setAttribute("alt", `Modelo 3D de ${title}`);
        }

        if (previewCode) previewCode.textContent = codigo;
        if (previewTitle) previewTitle.textContent = title;
        if (vehiclePreviewTitle) vehiclePreviewTitle.textContent = title;
        if (previewPrice) previewPrice.textContent = `$${formatNumber(precio)}`;
        if (previewType) previewType.textContent = tipo;
        if (previewFuel) previewFuel.textContent = combustible;
        if (previewTransmission) previewTransmission.textContent = transmision;
        if (previewMileage) previewMileage.textContent = `${formatNumber(kilometraje)} km`;
        if (previewDescription) previewDescription.textContent = descripcion || "Sin descripción disponible.";
        if (previewState) previewState.textContent = estado;
        if (previewStateText) previewStateText.textContent = estado;

        if (previewImage) {
            if (imagen) {
                previewImage.src = imagen;
                previewImage.alt = title;
                previewImage.style.display = "block";
            } else {
                previewImage.removeAttribute("src");
                previewImage.alt = "Vehículo sin imagen";
                previewImage.style.display = "none";
            }
        }

        if (previewModelShort) {
            previewModelShort.textContent = modelSrc ? (modelo3dId || "Modelo 3D asignado") : "Modelo 3D pendiente";
        }

        if (previewModelText) {
            previewModelText.textContent = modelSrc
                ? `Modelo asignado: ${modelo3dId || button.dataset.modelo3d}`
                : "Este vehículo todavía no tiene un archivo GLB/GLTF asignado.";
        }

        if (previewRegisterLink) {
            previewRegisterLink.classList.toggle("is-reserved", normalizeText(estado).includes("reservado"));
        }

        if (modelSrc) {
            setModelStatus("loading", "El modelo se cargará al abrir la pestaña Modelo 3D.");
        } else {
            setModelStatus("empty");
        }

        changeTab("technical");
        selectSystem("motor");
        setEditMode(false);

        if (editButton) {
            editButton.style.display = canEditPreview && activeSaveUrl ? "inline-flex" : "none";
        }

        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("preview-modal-open");

        renderIcons();
    }

    function closeModal() {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("preview-modal-open");

        if (modelViewer) {
            modelViewer.removeAttribute("src");
        }
    }

    previewButtons.forEach((button) => {
        button.addEventListener("click", (event) => {
            event.preventDefault();
            openModal(button);
        });
    });

    modal.querySelectorAll("[data-close-preview]").forEach((closeButton) => {
        closeButton.addEventListener("click", closeModal);
    });

    tabButtons.forEach((button) => {
        button.addEventListener("click", () => {
            changeTab(button.dataset.previewTab || "technical");
        });
    });

    systemButtons.forEach((button) => {
        button.addEventListener("click", () => {
            changeTab("model");
            selectSystem(button.dataset.system || "motor");
        });
    });

    if (resetCameraButton && modelViewer) {
        resetCameraButton.addEventListener("click", () => {
            ensureModelLoading();
            modelViewer.cameraOrbit = "35deg 72deg 7m";
            modelViewer.fieldOfView = "30deg";

            if (typeof modelViewer.jumpCameraToGoal === "function") {
                modelViewer.jumpCameraToGoal();
            }
        });
    }

    if (modelViewer) {
        modelViewer.addEventListener("load", () => {
            modelLoaded = true;
            setModelStatus("loaded");
        });

        modelViewer.addEventListener("error", () => {
            if (!modelLoaded && modelSrc) {
                setModelStatus("error");
            }
        });
    }

    if (editButton) {
        editButton.addEventListener("click", () => {
            changeTab("model");
            setEditMode(true);
        });
    }

    if (cancelButton) {
        cancelButton.addEventListener("click", () => {
            setEditMode(false);
        });
    }

    if (saveButton) {
        saveButton.addEventListener("click", savePreviewEdits);
    }

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && modal.classList.contains("is-open")) {
            closeModal();
        }
    });
}

