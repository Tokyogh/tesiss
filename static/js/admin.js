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
    // PREVENIR DOBLE ENVÍO EN FORMULARIOS
    // =============================

    const adminForms = document.querySelectorAll("form");

    adminForms.forEach((form) => {
        form.addEventListener("submit", () => {
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
});