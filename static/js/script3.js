document.addEventListener("DOMContentLoaded", () => {
    initVehiclePreviewModal();
    initLucideIcons();
    initDropdownMenus();
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
/* Misma lógica compatible con la navbar del index */
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
/* TARJETAS DE TIPO */
/* ============================= */

function initVehicleTypeButtons() {
    const typeButtons = document.querySelectorAll(".catalog-type-card");

    typeButtons.forEach((button) => {
        button.addEventListener("click", () => {
            typeButtons.forEach((item) => item.classList.remove("active"));
            button.classList.add("active");
        });
    });
}

/* ============================= */
/* TARJETAS DE RESUMEN */
/* ============================= */

function initStatCards() {
    const statCards = document.querySelectorAll(".catalog-stat-card");

    statCards.forEach((card) => {
        card.addEventListener("click", () => {
            statCards.forEach((item) => item.classList.remove("active"));
            card.classList.add("active");
        });
    });
}

/* ============================= */
/* FAVORITOS */
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
    const paginationButtons = document.querySelectorAll(".catalog-pagination .pagination-btn");

    paginationButtons.forEach((button) => {
        const text = button.textContent.trim();
        const isNumberButton = /^\d+$/.test(text);

        if (!isNumberButton) return;

        button.addEventListener("click", () => {
            paginationButtons.forEach((item) => {
                if (/^\d+$/.test(item.textContent.trim())) {
                    item.classList.remove("active");
                }
            });

            button.classList.add("active");
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
        const checkboxes = document.querySelectorAll('.catalog-sidebar input[type="checkbox"]');
        const textInputs = document.querySelectorAll('.catalog-sidebar input[type="text"]');
        const typeButtons = document.querySelectorAll(".catalog-type-card");
        const vehicleCards = document.querySelectorAll(".catalog-vehicle-card");
        const brandRows = document.querySelectorAll(".catalog-checkbox-row");

        checkboxes.forEach((checkbox) => {
            checkbox.checked = false;
        });

        textInputs.forEach((input) => {
            input.value = "";
        });

        typeButtons.forEach((button) => {
            button.classList.remove("active");
        });

        const firstType = document.querySelector(".catalog-type-card");
        if (firstType) {
            firstType.classList.add("active");
        }

        vehicleCards.forEach((card) => {
            card.style.display = "";
        });

        brandRows.forEach((row) => {
            row.style.display = "";
        });
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
            section.querySelector(".catalog-type-grid");

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

    if (!searchInput || vehicleCards.length === 0) return;

    searchInput.addEventListener("input", () => {
        const searchValue = normalizeText(searchInput.value);

        vehicleCards.forEach((card) => {
            const title = card.querySelector(".catalog-vehicle-main-info h3")?.textContent || "";
            const version = card.querySelector(".catalog-vehicle-main-info p")?.textContent || "";
            const specs = card.querySelector(".catalog-vehicle-specs")?.textContent || "";

            const cardText = normalizeText(`${title} ${version} ${specs}`);

            card.style.display = cardText.includes(searchValue) ? "" : "none";
        });
    });
}

/* ============================= */
/* BUSCADOR DE MARCAS */
/* ============================= */

function initBrandSearch() {
    const brandSearchInput = document.querySelector(".catalog-filter-search input");

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
/* NORMALIZAR TEXTO */
/* ============================= */

function normalizeText(text) {
    return text
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim();
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

    function formatNumber(value) {
        const number = Number(value || 0);
        return number.toLocaleString("en-US");
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
        const imagen = button.dataset.imagen || "";
        const modelo3d = button.dataset.modelo3d || "";
        const modelo3dId = button.dataset.modelo3dId || "";
        const descripcion = button.dataset.descripcion || "";

        previewCode.textContent = codigo;
        previewTitle.textContent = `${marca} ${modelo} ${anio}`.trim();
        previewSubtitle.textContent = `${tipo} · ${combustible} · ${transmision}`;
        previewPrice.textContent = `$${formatNumber(precio)}`;

        previewType.textContent = tipo;
        previewFuel.textContent = combustible;
        previewTransmission.textContent = transmision;
        previewMileage.textContent = `${formatNumber(kilometraje)} km`;

        previewDescription.textContent = descripcion || "Sin descripción disponible.";

        if (imagen) {
            previewImage.src = `/static/${imagen}`;
            previewImage.alt = `${marca} ${modelo} ${anio}`;
            previewImage.style.display = "block";
        } else {
            previewImage.removeAttribute("src");
            previewImage.alt = "Vehículo sin imagen";
            previewImage.style.display = "none";
        }

        if (modelo3d) {
            previewModelText.textContent = `Modelo asignado: ${modelo3dId || modelo3d}`;
        } else {
            previewModelText.textContent = "Modelo 3D pendiente de asignación.";
        }

        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");

        if (window.lucide) {
            lucide.createIcons();
        }
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