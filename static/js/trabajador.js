document.addEventListener("DOMContentLoaded", () => {
    initWorkerIcons();
    initWorkerSections();
    initWorkerSearch();
    initWorkerCopyButtons();
    initWorkerConfirmForms();
    initWorkerDisabledActions();
    initMaintenanceVehicleSearch();
    initWorkerDoubleSubmitGuard();
});

function initWorkerIcons() {
    if (window.lucide) {
        window.lucide.createIcons({
            attrs: {
                "stroke-width": 2
            }
        });
    }
}

function normalizeWorkerText(text) {
    return String(text || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim();
}

function showWorkerToast(message) {
    const toast = document.getElementById("workerToast");

    if (!toast) return;

    toast.textContent = message;
    toast.classList.add("show");

    window.clearTimeout(toast.dataset.timeoutId);

    const timeoutId = window.setTimeout(() => {
        toast.classList.remove("show");
    }, 2600);

    toast.dataset.timeoutId = String(timeoutId);
}

function initWorkerSections() {
    const sections = document.querySelectorAll("[data-worker-content]");
    const allLinks = document.querySelectorAll("[data-worker-section]");
    const sidebarLinks = document.querySelectorAll(".worker-sidebar [data-worker-section]");

    function showSection(sectionName, updateHash = true) {
        if (!sectionName) return;

        const target = document.querySelector(`[data-worker-content="${sectionName}"]`);

        if (!target) return;

        sections.forEach((section) => section.classList.remove("active"));
        target.classList.add("active");

        sidebarLinks.forEach((link) => link.classList.remove("active"));

        const activeSidebarLink = document.querySelector(
            `.worker-sidebar [data-worker-section="${sectionName}"]`
        );

        if (activeSidebarLink) {
            activeSidebarLink.classList.add("active");
        }

        if (updateHash) {
            const newHash = `#trabajador-${sectionName}`;

            if (window.location.hash !== newHash) {
                history.pushState(null, "", newHash);
            }
        }

        window.scrollTo({
            top: 0,
            behavior: "smooth"
        });

        initWorkerIcons();
    }

    allLinks.forEach((link) => {
        link.addEventListener("click", (event) => {
            const sectionName = link.dataset.workerSection;
            const target = document.querySelector(`[data-worker-content="${sectionName}"]`);

            if (!sectionName || !target) return;

            event.preventDefault();
            showSection(sectionName);
        });
    });

    function getSectionFromHash() {
        const hash = window.location.hash.replace("#", "");

        if (!hash) return null;

        if (hash.startsWith("trabajador-")) {
            return hash.replace("trabajador-", "");
        }

        return null;
    }

    showSection(getSectionFromHash() || "inicio", false);

    window.addEventListener("popstate", () => {
        showSection(getSectionFromHash() || "inicio", false);
    });
}

function initWorkerSearch() {
    const inputs = document.querySelectorAll("[data-worker-search]");

    inputs.forEach((input) => {
        input.addEventListener("input", () => {
            const listName = input.dataset.workerSearch;
            const list = document.querySelector(`[data-worker-list="${listName}"]`);

            if (!list) return;

            const searchValue = normalizeWorkerText(input.value);
            const items = list.querySelectorAll("[data-worker-item]");

            items.forEach((item) => {
                const text = normalizeWorkerText(item.textContent);

                if (!searchValue || text.includes(searchValue)) {
                    item.classList.remove("is-hidden");
                } else {
                    item.classList.add("is-hidden");
                }
            });
        });
    });
}

function initWorkerCopyButtons() {
    const copyButtons = document.querySelectorAll("[data-copy-code]");

    copyButtons.forEach((button) => {
        button.addEventListener("click", async () => {
            const code = button.dataset.copyCode || "";

            if (!code) return;

            try {
                await navigator.clipboard.writeText(code);
                showWorkerToast("Código copiado al portapapeles.");
            } catch (error) {
                const temporalInput = document.createElement("input");
                temporalInput.value = code;
                document.body.appendChild(temporalInput);
                temporalInput.select();
                document.execCommand("copy");
                temporalInput.remove();
                showWorkerToast("Código copiado.");
            }
        });
    });
}

function initWorkerConfirmForms() {
    const forms = document.querySelectorAll("[data-worker-confirm]");

    forms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            const message = form.dataset.workerConfirm || "¿Confirmar esta acción?";

            if (!confirm(message)) {
                event.preventDefault();
            }
        });
    });
}

function initWorkerDisabledActions() {
    const buttons = document.querySelectorAll(".worker-disabled-action");

    buttons.forEach((button) => {
        button.addEventListener("click", (event) => {
            event.preventDefault();
            showWorkerToast("Esta función se conectará en una siguiente fase.");
        });
    });
}

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

function initWorkerDoubleSubmitGuard() {
    const forms = document.querySelectorAll("form");

    forms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (event.defaultPrevented) return;

            const submitButton = form.querySelector('button[type="submit"]');

            if (!submitButton) return;

            submitButton.disabled = true;
            submitButton.dataset.originalText = submitButton.textContent.trim();
            submitButton.textContent = "Procesando...";
        });
    });
}
