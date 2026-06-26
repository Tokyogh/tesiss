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

    sidebarLinks.forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();

            const sectionName = link.dataset.section;

            if (sectionName) {
                mostrarSeccion(sectionName);
            }
        });
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
});