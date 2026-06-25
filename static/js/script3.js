document.addEventListener("DOMContentLoaded", () => {
    initLucideIcons();
    initDropdownMenus();
    initVehicleTypeButtons();
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
/* Compatible con la navbar del index */
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
/* TIPOS DE VEHÍCULO */
/* ============================= */

function initVehicleTypeButtons() {
    const typeButtons = document.querySelectorAll(".catalog-type-card");

    typeButtons.forEach((button) => {
        button.addEventListener("click", () => {
            typeButtons.forEach((item) => {
                item.classList.remove("active");
            });

            button.classList.add("active");
        });
    });
}

/* ============================= */
/* FAVORITOS */
/* ============================= */

function initFavoriteButtons() {
    const favoriteButtons = document.querySelectorAll(".favorite-btn");

    favoriteButtons.forEach((button) => {
        button.addEventListener("click", () => {
            button.classList.toggle("active");

            const icon = button.querySelector("svg");

            if (!icon) return;

            if (button.classList.contains("active")) {
                icon.setAttribute("fill", "currentColor");
            } else {
                icon.setAttribute("fill", "none");
            }
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
                const itemText = item.textContent.trim();

                if (/^\d+$/.test(itemText)) {
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
        const titleRow = section.querySelector(".catalog-filter-title");

        if (!titleRow) return;

        const hasCollapsibleContent =
            section.querySelector(".catalog-checkbox-list") ||
            section.querySelector(".catalog-filter-search") ||
            section.querySelector(".catalog-range-control") ||
            section.querySelector(".catalog-year-filter");

        if (!hasCollapsibleContent) return;

        const icon = titleRow.querySelector("svg");

        if (icon) {
            icon.style.transition = "transform 0.25s ease";
        }

        titleRow.addEventListener("click", () => {
            section.classList.toggle("is-collapsed");

            const currentIcon = titleRow.querySelector("svg");

            if (!currentIcon) return;

            const iconName = currentIcon.getAttribute("data-lucide");
            const isCollapsed = section.classList.contains("is-collapsed");

            if (iconName === "chevron-up") {
                currentIcon.style.transform = isCollapsed ? "rotate(180deg)" : "rotate(0deg)";
            }

            if (iconName === "chevron-down") {
                currentIcon.style.transform = isCollapsed ? "rotate(0deg)" : "rotate(180deg)";
            }
        });
    });
}

/* ============================= */
/* BUSCADOR PRINCIPAL DEL CATÁLOGO */
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

            if (cardText.includes(searchValue)) {
                card.style.display = "";
            } else {
                card.style.display = "none";
            }
        });
    });
}

/* ============================= */
/* BUSCADOR DE MARCAS EN SIDEBAR */
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

            if (rowText.includes(searchValue)) {
                row.style.display = "";
            } else {
                row.style.display = "none";
            }
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