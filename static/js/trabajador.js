document.addEventListener("DOMContentLoaded", () => {
    initWorkerIcons();
    initWorkerSections();
    initWorkerSearch();
    initWorkerCopyButtons();
    initWorkerConfirmForms();
    initWorkerDisabledActions();
    initMaintenanceVehicleSearch();
    initWorkerCatalogCodeGenerator();
    initWorkerFileFields();
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


function initWorkerCatalogCodeGenerator() {
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
}


function initWorkerFileFields() {
    const inputs = document.querySelectorAll('.vinova-file-field input[type="file"], .articulo-file-field input[type="file"], .worker-field input[type="file"]');

    inputs.forEach((input) => {
        if (input.dataset.vinovaFileReady === "1") return;
        input.dataset.vinovaFileReady = "1";

        const field = input.closest('.vinova-file-field, .articulo-file-field, .worker-field');
        const help = field?.querySelector('small[data-articulo-file-name], small:last-of-type');

        if (help && !help.dataset.vinovaOriginalHelp) {
            help.dataset.vinovaOriginalHelp = help.textContent.trim();
        }

        input.addEventListener('change', () => {
            const file = input.files && input.files[0];
            if (!help) return;

            if (!file) {
                help.textContent = help.dataset.vinovaOriginalHelp || 'Selecciona un archivo.';
                field?.classList.remove('has-selected-file');
                return;
            }

            help.textContent = `Archivo seleccionado: ${file.name}`;
            field?.classList.add('has-selected-file');
        });
    });
}
