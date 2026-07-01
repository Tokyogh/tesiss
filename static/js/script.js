//Esta parte controla el comportamiento del dropdown al pasar el mouse por encima y al salir del área del dropdown. Cuando el mouse entra en el área del dropdown, se muestra el menú desplegable. Cuando el mouse sale del área, se oculta el menú después de un breve retraso (200 ms).
document.querySelectorAll('.dropdown').forEach(dropdown => {
    const menu = dropdown.querySelector('.dropdown-menu');
    let timeout;

    dropdown.addEventListener('mouseenter', () => {
        clearTimeout(timeout);
        menu.classList.add('show');
    });

    dropdown.addEventListener('mouseleave', () => {
        timeout = setTimeout(() => {
            menu.classList.remove('show');
        }, 200); // 200 ms
    });
});

// Activar los iconos de Lucide
if (window.lucide) {
    lucide.createIcons();
}


// =============================
// PREVIEW 3D VINOVA
// =============================
(function initVinovaVehiclePreview() {
    const openButton = document.getElementById("openVehiclePreview");
    const modal = document.getElementById("vehiclePreviewModal");

    if (!openButton || !modal) return;

    const closeElements = modal.querySelectorAll("[data-close-preview]");
    const tabButtons = modal.querySelectorAll("[data-preview-tab]");
    const body = modal.querySelector(".vehicle-preview-body");
    const systemButtons = modal.querySelectorAll("[data-system]");
    const modeLabel = document.getElementById("previewModeLabel");
    const modelViewer = document.getElementById("vinovaPreviewModel");
    const resetCameraButton = document.getElementById("resetVehicleCamera");
    const modelStatus = document.getElementById("demoModelStatus");

    const systemIcon = document.getElementById("previewSystemIcon");
    const systemName = document.getElementById("previewSystemName");
    const systemSpec = document.getElementById("previewSystemSpec");
    const systemDescription = document.getElementById("previewSystemDescription");
    const systemLocation = document.getElementById("previewSystemLocation");
    const systemPrices = document.getElementById("previewSystemPrices");

    const systems = {
        motor: {
            icon: "settings",
            name: "Sistema de motor",
            spec: "Motor 1.6L, 4 cilindros, gasolina",
            description: "Conjunto encargado de generar la potencia principal del vehículo y transmitirla al sistema de tracción.",
            location: "Compartimiento frontal del vehículo.",
            prices: [
                ["Filtro de aceite", "$12 - $25"],
                ["Bujías", "$20 - $60"],
                ["Banda de accesorios", "$35 - $90"]
            ]
        },
        transmision: {
            icon: "git-branch",
            name: "Sistema de transmisión",
            spec: "Caja automática de 6 velocidades",
            description: "Administra la entrega de potencia desde el motor hacia las ruedas para mantener un manejo eficiente.",
            location: "Zona inferior central, conectada al bloque del motor.",
            prices: [
                ["Aceite de transmisión", "$35 - $90"],
                ["Filtro de caja", "$28 - $75"],
                ["Kit de embrague", "$180 - $520"]
            ]
        },
        frenos: {
            icon: "disc-3",
            name: "Sistema de frenos",
            spec: "Discos ventilados delanteros y sistema ABS",
            description: "Permite reducir la velocidad y detener el vehículo con asistencia electrónica de seguridad.",
            location: "Ruedas delanteras y traseras, con módulo hidráulico en el vano motor.",
            prices: [
                ["Pastillas delanteras", "$35 - $110"],
                ["Discos de freno", "$80 - $240"],
                ["Líquido de frenos", "$8 - $25"]
            ]
        },
        suspension: {
            icon: "activity",
            name: "Sistema de suspensión",
            spec: "Suspensión independiente con amortiguadores hidráulicos",
            description: "Absorbe irregularidades del camino y mantiene estabilidad, confort y contacto con la calzada.",
            location: "Conjunto de ruedas, ejes y bastidor inferior.",
            prices: [
                ["Amortiguador", "$55 - $180"],
                ["Bieletas", "$18 - $60"],
                ["Bujes", "$12 - $45"]
            ]
        },
        direccion: {
            icon: "circle-dot",
            name: "Sistema de dirección",
            spec: "Dirección asistida eléctricamente",
            description: "Controla el ángulo de las ruedas delanteras y mejora la maniobrabilidad del vehículo.",
            location: "Columna de dirección, cremallera y tren delantero.",
            prices: [
                ["Terminal de dirección", "$22 - $70"],
                ["Rótula", "$20 - $65"],
                ["Cremallera", "$220 - $650"]
            ]
        },
        electrico: {
            icon: "zap",
            name: "Sistema eléctrico",
            spec: "Red de 12V con alternador y módulo ECU",
            description: "Alimenta sensores, luces, módulos electrónicos, arranque y sistemas auxiliares del vehículo.",
            location: "Distribuido en todo el vehículo; batería y fusilera en zona frontal.",
            prices: [
                ["Batería", "$95 - $220"],
                ["Alternador", "$160 - $420"],
                ["Sensor común", "$25 - $140"]
            ]
        },
        carroceria: {
            icon: "car-front",
            name: "Sistema de carrocería",
            spec: "Estructura monocasco con paneles exteriores",
            description: "Protege a los ocupantes, sostiene componentes externos y define aerodinámica y diseño del vehículo.",
            location: "Estructura exterior e interior del vehículo.",
            prices: [
                ["Parachoques", "$120 - $420"],
                ["Faro delantero", "$90 - $380"],
                ["Guardafango", "$75 - $260"]
            ]
        }
    };

    let modelLoadStarted = false;
    let modelLoaded = false;

    function renderIcons() {
        if (window.lucide) {
            window.lucide.createIcons();
        }
    }

    function setModelStatus(state) {
        if (!modelStatus) return;

        modelStatus.classList.remove("is-loading", "is-loaded", "is-hidden", "has-error");

        if (state === "loading") {
            modelStatus.classList.add("is-loading");
            modelStatus.innerHTML = `
                <i data-lucide="loader"></i>
                <strong>Cargando modelo 3D</strong>
                <p>Estamos preparando el archivo GLB. Puedes seguir revisando la información general mientras termina de cargar.</p>
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
                <p>Verifica que el archivo exista en <code>static/models/demo/demo-car.glb</code>.</p>
            `;
        }

        renderIcons();
    }

    function ensureModelLoading() {
        if (!modelViewer || modelLoadStarted) return;

        const modelSrc = modelViewer.dataset.modelSrc;

        if (!modelSrc) return;

        modelLoadStarted = true;
        setModelStatus("loading");

        // Carga diferida: no pesa al entrar al home, empieza al abrir el preview.
        window.setTimeout(() => {
            if (!modelViewer.getAttribute("src")) {
                modelViewer.setAttribute("src", modelSrc);
            }
        }, 250);
    }

    function openPreview() {
        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("preview-modal-open");
        openButton.setAttribute("aria-expanded", "true");
        renderIcons();

        // Mientras el usuario lee la información general, el 3D empieza a cargarse en segundo plano.
        if ("requestIdleCallback" in window) {
            window.requestIdleCallback(ensureModelLoading, { timeout: 900 });
        } else {
            window.setTimeout(ensureModelLoading, 700);
        }
    }

    function closePreview() {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("preview-modal-open");
        openButton.setAttribute("aria-expanded", "false");
    }

    function changeTab(tabName) {
        tabButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.previewTab === tabName);
        });

        if (body) {
            body.dataset.previewCurrentTab = tabName;
        }

        if (modeLabel) {
            modeLabel.textContent = tabName === "model"
                ? "Modelo 3D interactivo con ficha técnica por sistemas"
                : "Información general del vehículo";
        }

        if (tabName === "model") {
            ensureModelLoading();
        }
    }

    function selectSystem(systemKey) {
        const data = systems[systemKey] || systems.motor;

        systemButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.system === systemKey);
        });

        if (systemIcon) systemIcon.setAttribute("data-lucide", data.icon);
        if (systemName) systemName.textContent = data.name;
        if (systemSpec) systemSpec.textContent = data.spec;
        if (systemDescription) systemDescription.textContent = data.description;
        if (systemLocation) systemLocation.textContent = data.location;

        if (systemPrices) {
            systemPrices.innerHTML = data.prices
                .map(([part, price]) => `<li><span>${part}</span><strong>${price}</strong></li>`)
                .join("");
        }

        renderIcons();
    }

    openButton.setAttribute("aria-controls", "vehiclePreviewModal");
    openButton.setAttribute("aria-expanded", "false");
    openButton.addEventListener("click", openPreview);

    closeElements.forEach((element) => {
        element.addEventListener("click", closePreview);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && modal.classList.contains("is-open")) {
            closePreview();
        }
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
            if (!modelLoaded) {
                setModelStatus("error");
            }
        });
    }

    selectSystem("motor");
})();
