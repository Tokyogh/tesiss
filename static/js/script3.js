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

function initStatCards() {
    const statCards = document.querySelectorAll(".catalog-stat-card[data-filter-field]");

    statCards.forEach((card) => {
        card.addEventListener("click", () => {
            const field = card.dataset.filterField;
            const value = card.dataset.filterValue || "";
            const url = new URL(window.location.href);

            url.searchParams.delete("page");

            if (!field) {
                window.location.href = url.toString();
                return;
            }

            const values = url.searchParams.getAll(field);
            url.searchParams.delete(field);

            const alreadyActive = values.includes(value);

            if (!alreadyActive && value) {
                url.searchParams.append(field, value);
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

    const previewImage = document.getElementById("previewImage");
    const previewCode = document.getElementById("previewCode");
    const previewTitle = document.getElementById("previewTitle");
    const previewSubtitle = document.getElementById("previewSubtitle");
    const previewPrice = document.getElementById("previewPrice");
    const previewType = document.getElementById("previewType");
    const previewFuel = document.getElementById("previewFuel");
    const previewTransmission = document.getElementById("previewTransmission");
    const previewMileage = document.getElementById("previewMileage");
    const previewDescription = document.getElementById("previewDescription");
    const previewModelText = document.getElementById("previewModelText");
    const previewState = document.getElementById("previewState");
    const previewRegisterLink = document.getElementById("previewRegisterLink");

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
        const modelo3d = button.dataset.modelo3d || "";
        const modelo3dId = button.dataset.modelo3dId || "";
        const descripcion = button.dataset.descripcion || "";
        const estado = button.dataset.estado || "Disponible";

        if (previewCode) previewCode.textContent = codigo;
        if (previewTitle) previewTitle.textContent = `${marca} ${modelo} ${anio}`.trim() || "Vehículo";
        if (previewSubtitle) previewSubtitle.textContent = `${tipo} · ${combustible} · ${transmision}`;
        if (previewPrice) previewPrice.textContent = `$${formatNumber(precio)}`;
        if (previewType) previewType.textContent = tipo;
        if (previewFuel) previewFuel.textContent = combustible;
        if (previewTransmission) previewTransmission.textContent = transmision;
        if (previewMileage) previewMileage.textContent = `${formatNumber(kilometraje)} km`;
        if (previewDescription) previewDescription.textContent = descripcion || "Sin descripción disponible.";

        if (previewState) {
            previewState.classList.toggle("reserved", normalizeText(estado).includes("reservado"));
            previewState.querySelector("strong").textContent = estado;
        }

        if (previewImage) {
            if (imagen) {
                previewImage.src = imagen;
                previewImage.alt = `${marca} ${modelo} ${anio}`.trim() || "Vehículo VINOVA";
                previewImage.style.display = "block";
            } else {
                previewImage.removeAttribute("src");
                previewImage.alt = "Vehículo sin imagen";
                previewImage.style.display = "none";
            }
        }

        if (previewModelText) {
            previewModelText.textContent = modelo3d
                ? `Modelo asignado: ${modelo3dId || modelo3d}`
                : "Modelo 3D pendiente de asignación.";
        }

        if (previewRegisterLink) {
            previewRegisterLink.textContent = normalizeText(estado).includes("reservado")
                ? "Solicitar registro"
                : "Registrar en mi perfil";
        }

        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");

        initLucideIcons();
    }

    function closeModal() {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");
    }

    previewButtons.forEach((button) => {
        button.addEventListener("click", (event) => {
            event.preventDefault();
            openModal(button);
        });
    });

    document.querySelectorAll("[data-close-preview]").forEach((closeButton) => {
        closeButton.addEventListener("click", closeModal);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && modal.classList.contains("is-open")) {
            closeModal();
        }
    });
}
