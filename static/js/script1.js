document.addEventListener("DOMContentLoaded", () => {
    const sidebarLinks = document.querySelectorAll(".sidebar-link");
    const sections = document.querySelectorAll(".dashboard-section");

    const fotoInput = document.getElementById("foto_perfil");
    const preview = document.getElementById("profilePhotoPreview");

    const searchInput = document.querySelector(".header-right input");
    const notificationIcon = document.querySelector(".header-right .fa-bell");

    // ================= CAMBIAR SECCIONES DESDE SIDEBAR =================

    function mostrarSeccion(sectionName) {
        sections.forEach((section) => {
            section.classList.remove("active-section");
        });

        sidebarLinks.forEach((link) => {
            link.classList.remove("active");
        });

        const sectionToShow = document.querySelector(`[data-content="${sectionName}"]`);
        const activeLink = document.querySelector(`[data-section="${sectionName}"]`);

        if (sectionToShow) {
            sectionToShow.classList.add("active-section");
        }

        if (activeLink) {
            activeLink.classList.add("active");
        }

        window.location.hash = `seccion-${sectionName}`;

        window.scrollTo({
            top: 0,
            behavior: "smooth"
        });
    }

    document.addEventListener("click", (event) => {
        const link = event.target.closest(".sidebar-link");

        if (!link) return;

        const sectionName = link.dataset.section;

        if (!sectionName) return;

        event.preventDefault();
        mostrarSeccion(sectionName);
    });

    // ================= ABRIR SECCIÓN SEGÚN HASH =================

    function cargarSeccionDesdeHash() {
        const hash = window.location.hash.replace("#seccion-", "");

        if (hash) {
            const sectionExists = document.querySelector(`[data-content="${hash}"]`);

            if (sectionExists) {
                mostrarSeccion(hash);
                return;
            }
        }

        mostrarSeccion("inicio");
    }

    cargarSeccionDesdeHash();

    // ================= PREVIEW DE FOTO DE PERFIL =================

    if (fotoInput && preview) {
        fotoInput.addEventListener("change", () => {
            const file = fotoInput.files[0];

            if (!file) return;

            const allowedTypes = ["image/jpeg", "image/png", "image/webp"];

            if (!allowedTypes.includes(file.type)) {
                alert("Formato no permitido. Usa JPG, PNG o WEBP.");
                fotoInput.value = "";
                return;
            }

            const maxSize = 25 * 1024 * 1024;

            if (file.size > maxSize) {
                alert("La imagen es demasiado pesada.");
                fotoInput.value = "";
                return;
            }

            const reader = new FileReader();

            reader.onload = (event) => {
                preview.innerHTML = `
                    <img src="${event.target.result}" alt="Vista previa de foto de perfil">
                `;
            };

            reader.readAsDataURL(file);
        });
    }

    // ================= CAMPANA ABRE NOTIFICACIONES =================

    if (notificationIcon) {
        notificationIcon.addEventListener("click", () => {
            mostrarSeccion("notificaciones");
        });
    }

    // ================= BUSCADOR SIMPLE DE VEHÍCULOS =================

    if (searchInput) {
        searchInput.addEventListener("focus", () => {
            mostrarSeccion("mis-vehiculos");
        });

        searchInput.addEventListener("input", () => {
            const searchValue = searchInput.value.toLowerCase().trim();
            const vehicleCards = document.querySelectorAll(".vehicle-card");

            vehicleCards.forEach((card) => {
                const text = card.textContent.toLowerCase();

                if (text.includes(searchValue)) {
                    card.style.display = "";
                } else {
                    card.style.display = "none";
                }
            });
        });
    }


    // ================= MANTENIMIENTO =================

    const vehicleSelect = document.getElementById("usuario_vehiculo_id");
    const kmInput = document.getElementById("kilometraje");

    if (vehicleSelect && kmInput) {
        vehicleSelect.addEventListener("change", () => {
            const selectedOption = vehicleSelect.options[vehicleSelect.selectedIndex];
            const currentKm = selectedOption ? selectedOption.dataset.currentKm : "";

            if (currentKm && !kmInput.value) {
                kmInput.value = currentKm;
            }
        });
    }

    document.querySelectorAll("[data-confirm-delete]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            const message = form.dataset.confirmDelete || "¿Eliminar este registro?";

            if (!confirm(message)) {
                event.preventDefault();
            }
        });
    });

    // ================= MODAL DETALLE VEHÍCULO =================

    const vehicleModals = document.querySelectorAll(".profile-vehicle-modal");

    function openVehicleModal(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        vehicleModals.forEach((item) => {
            item.classList.remove("is-open");
            item.setAttribute("aria-hidden", "true");
        });

        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("vehicle-modal-open");

        const firstTab = modal.querySelector("[data-vehicle-tab]");
        if (firstTab) {
            firstTab.click();
        }
    }

    function closeVehicleModal() {
        vehicleModals.forEach((modal) => {
            modal.classList.remove("is-open");
            modal.setAttribute("aria-hidden", "true");
        });

        document.body.classList.remove("vehicle-modal-open");
    }

    document.addEventListener("click", (event) => {
        const openButton = event.target.closest("[data-open-vehicle-modal]");

        if (openButton) {
            event.preventDefault();
            openVehicleModal(openButton.dataset.openVehicleModal);
            return;
        }

        if (event.target.closest("[data-close-vehicle-modal]")) {
            event.preventDefault();
            closeVehicleModal();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeVehicleModal();
        }
    });

    document.querySelectorAll(".profile-vehicle-modal").forEach((modal) => {
        const tabs = modal.querySelectorAll("[data-vehicle-tab]");
        const panels = modal.querySelectorAll("[data-vehicle-panel]");

        tabs.forEach((tab) => {
            tab.addEventListener("click", () => {
                const targetPanel = tab.dataset.vehicleTab;

                tabs.forEach((item) => item.classList.remove("active"));
                tab.classList.add("active");

                panels.forEach((panel) => {
                    const isActive = panel.dataset.vehiclePanel === targetPanel;
                    panel.hidden = !isActive;
                });
            });
        });
    });



    // ================= GRÁFICA HISTORIAL DE MANTENIMIENTOS =================

    const maintenanceChartCanvas = document.getElementById("profileMaintenanceChart");

    if (maintenanceChartCanvas && window.Chart) {
        const chartData = window.VINOVA_PROFILE_CHART || { labels: [], values: [] };
        const labels = Array.isArray(chartData.labels) ? chartData.labels : [];
        const values = Array.isArray(chartData.values) ? chartData.values : [];
        const ctx = maintenanceChartCanvas.getContext("2d");
        const gradient = ctx.createLinearGradient(0, 0, 0, maintenanceChartCanvas.offsetHeight || 220);
        gradient.addColorStop(0, "rgba(59, 130, 246, 0.42)");
        gradient.addColorStop(1, "rgba(59, 130, 246, 0.02)");

        new Chart(ctx, {
            type: "line",
            data: {
                labels,
                datasets: [{
                    data: values,
                    tension: 0.42,
                    fill: true,
                    borderWidth: 3,
                    borderColor: "#2563eb",
                    backgroundColor: gradient,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointBorderWidth: 2,
                    pointBackgroundColor: "#60a5fa",
                    pointBorderColor: "#0f172a"
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "rgba(2, 8, 20, 0.92)",
                        borderColor: "rgba(96, 165, 250, 0.22)",
                        borderWidth: 1,
                        titleColor: "#ffffff",
                        bodyColor: "#cbd5e1",
                        displayColors: false,
                        callbacks: {
                            label: (context) => `${context.parsed.y} mantenimiento(s)`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: "rgba(148, 163, 184, 0.08)" },
                        ticks: { color: "#8ea0b8", font: { size: 11, weight: "700" } }
                    },
                    y: {
                        beginAtZero: true,
                        precision: 0,
                        grid: { color: "rgba(148, 163, 184, 0.08)" },
                        ticks: {
                            color: "#8ea0b8",
                            stepSize: 1,
                            font: { size: 11, weight: "700" }
                        }
                    }
                }
            }
        });
    }

});
