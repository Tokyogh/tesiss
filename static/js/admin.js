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
        resultsBox.hidden = false;
        resultsBox.innerHTML = `<div class="maintenance-results-message ${type}">${message}</div>`;
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

            if (!searchUrl || !input || !hiddenInput || !resultsBox || !selectedBox || !form) return;

            let controller = null;

            function clearSelection() {
                hiddenInput.value = "";
                input.value = "";
                selectedBox.classList.add("is-empty");
                selectedBox.innerHTML = "Ningún cliente/vehículo seleccionado.";
                resultsBox.hidden = true;
                resultsBox.innerHTML = "";
                input.focus();
            }

            function selectResult(result) {
                hiddenInput.value = result.usuario_vehiculo_id || "";
                input.value = result.label || "";
                selectedBox.classList.remove("is-empty");
                selectedBox.innerHTML = `
                    <strong>${result.usuario_nombre || "Cliente"}</strong>
                    <span>${result.usuario_correo || "Sin correo"}</span>
                    <small>${result.vehiculo || "Vehículo"} · ID vehículo: ${result.vehiculo_id || "N/D"} · Registro: ${result.usuario_vehiculo_id || "N/D"}</small>
                    <small>${result.codigo_catalogo || "Sin código"} · ${result.kilometraje_referencia_visible || "0"} km de referencia</small>
                `;
                resultsBox.hidden = true;
                resultsBox.innerHTML = "";

                const kmInput = form.querySelector('input[name="kilometraje_actual"]');
                if (kmInput && result.kilometraje_referencia !== undefined && (!kmInput.value || Number(kmInput.value) === 0)) {
                    kmInput.value = result.kilometraje_referencia;
                }
            }

            async function searchVehicles() {
                const query = input.value.trim();
                hiddenInput.value = "";
                selectedBox.classList.add("is-empty");
                selectedBox.innerHTML = "Ningún cliente/vehículo seleccionado.";

                if (query.length < 2) {
                    resultsBox.hidden = true;
                    resultsBox.innerHTML = "";
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

                    resultsBox.hidden = false;
                    resultsBox.innerHTML = results.map((result) => `
                        <button type="button" class="maintenance-result-item" data-maintenance-result-id="${result.usuario_vehiculo_id}">
                            <strong>${result.usuario_nombre || "Cliente"}</strong>
                            <span>${result.usuario_correo || "Sin correo"}</span>
                            <small>${result.vehiculo || "Vehículo"} · ID vehículo: ${result.vehiculo_id || "N/D"} · Registro: ${result.usuario_vehiculo_id || "N/D"}</small>
                            <small>${result.codigo_catalogo || "Sin código"} · ${result.kilometraje_referencia_visible || "0"} km</small>
                        </button>
                    `).join("");

                    resultsBox.querySelectorAll("[data-maintenance-result-id]").forEach((button) => {
                        button.addEventListener("click", () => {
                            const selected = results.find((result) => String(result.usuario_vehiculo_id) === String(button.dataset.maintenanceResultId));
                            if (selected) selectResult(selected);
                        });
                    });
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
                    setMaintenanceMessage(resultsBox, "Selecciona un resultado de la búsqueda antes de registrar el mantenimiento.", "warning");
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
});