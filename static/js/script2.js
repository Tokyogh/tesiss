/* =========================
  Scripts login
   ========================= */

document.addEventListener("DOMContentLoaded", () => {
    iniciarModales();
    iniciarPasswordToggle();
    iniciarRippleLogin();
    iniciarCursorGlow();
    iniciarLoginCardMotion();
    iniciarThemeToggle();
});

/* =========================
   Helpers
   ========================= */

function obtenerModal(idModal) {
    const equivalencias = {
        modalRecuperar: "modal",
        modalRegistro: "modal-registro",
        modalSoporte: "modal-soporte",
        modalContacto: "modal-contacto",
        modalNosotros: "modal-nosotros"
    };

    return (
        document.getElementById(idModal) ||
        document.getElementById(equivalencias[idModal])
    );
}

function mostrarModal(modal) {
    if (!modal) return;

    modal.style.display = "flex";
    modal.classList.add("active");
    document.body.style.overflow = "hidden";
}

function ocultarModal(modal) {
    if (!modal) return;

    modal.style.display = "none";
    modal.classList.remove("active");

    const hayModalActivo = document.querySelector(".modal.active");

    if (!hayModalActivo) {
        document.body.style.overflow = "";
    }
}

/* =========================
   Modales
   ========================= */

function iniciarModales() {
    const abrirRecuperar = document.getElementById("abrirRecuperar");
    const abrirRegistroBtn = document.getElementById("abrirRegistro");

    if (abrirRecuperar) {
        abrirRecuperar.addEventListener("click", (e) => {
            e.preventDefault();
            abrirModal();
        });
    }

    if (abrirRegistroBtn) {
        abrirRegistroBtn.addEventListener("click", (e) => {
            e.preventDefault();
            abrirRegistro();
        });
    }

    document.querySelectorAll(".modal").forEach((modal) => {
        modal.addEventListener("click", (e) => {
            if (e.target === modal) {
                ocultarModal(modal);
            }
        });
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            document.querySelectorAll(".modal").forEach((modal) => {
                ocultarModal(modal);
            });
        }
    });
}

/* =========================
   RECUPERAR CONTRASEÑA
   Compatible con:
   abrirModal()
   abrirModal("modal")
   abrirModal("modalRecuperar")
   ========================= */

function abrirModal(idModal = "modal") {
    const modal = obtenerModal(idModal);
    mostrarModal(modal);
}

function cerrarModal(idModal = "modal") {
    const modal = obtenerModal(idModal);
    ocultarModal(modal);
}

/* =========================
   REGISTRO
   ========================= */

function abrirRegistro() {
    const modal = obtenerModal("modal-registro");
    mostrarModal(modal);
}

function cerrarRegistro() {
    const modal = obtenerModal("modal-registro");
    ocultarModal(modal);
}

/* =========================
   SOPORTE
   ========================= */

function abrirSoporte() {
    const modal = obtenerModal("modal-soporte");
    mostrarModal(modal);
}

function cerrarSoporte() {
    const modal = obtenerModal("modal-soporte");
    ocultarModal(modal);
}

/* =========================
   CONTACTO
   ========================= */

function abrirContacto() {
    const modal = obtenerModal("modal-contacto");
    mostrarModal(modal);
}

function cerrarContacto() {
    const modal = obtenerModal("modal-contacto");
    ocultarModal(modal);
}

/* =========================
   SOBRE NOSOTROS
   ========================= */

function abrirNosotros() {
    const modal = obtenerModal("modal-nosotros");
    mostrarModal(modal);
}

function cerrarNosotros() {
    const modal = obtenerModal("modal-nosotros");
    ocultarModal(modal);
}

/* =========================
   Mostrar / ocultar contraseña
   Compatible con:
   .eye
   .toggle-pass
   .toggle-pass i
   ========================= */

function iniciarPasswordToggle() {
    document.querySelectorAll(".toggle-pass, .eye").forEach((icon) => {
        if (icon.dataset.toggleReady === "1") return;

        icon.dataset.toggleReady = "1";
        icon.addEventListener("click", () => togglePassword(icon));

        icon.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                togglePassword(icon);
            }
        });
    });
}

function obtenerInputPassword(icon) {
    if (!icon) return document.getElementById("password");

    const targetId = icon.dataset.target || icon.getAttribute("data-target");

    if (targetId) {
        return document.getElementById(targetId);
    }

    const contenedor = icon.closest(".input-box, .modal-password-box");

    if (contenedor) {
        return contenedor.querySelector('input[type="password"], input[type="text"]');
    }

    return document.getElementById("password");
}

function togglePassword(icon = null) {
    const trigger = icon && icon.classList ? icon : document.querySelector(".toggle-pass, .eye");
    const input = obtenerInputPassword(trigger);

    if (!input || !trigger) return;

    const mostrar = input.type === "password";
    input.type = mostrar ? "text" : "password";

    trigger.classList.toggle("fa-eye", !mostrar);
    trigger.classList.toggle("fa-eye-slash", mostrar);

    const etiqueta = mostrar ? "Ocultar contraseña" : "Mostrar contraseña";
    trigger.setAttribute("aria-label", etiqueta);
    trigger.setAttribute("title", etiqueta);
}

/* =========================
   Efecto ripple en botón login
   Compatible con:
   .login-btn
   .btn-login
   ========================= */

function iniciarRippleLogin() {
    const loginBtn =
        document.querySelector(".login-btn") ||
        document.querySelector(".btn-login");

    if (!loginBtn) return;

    loginBtn.addEventListener("click", (e) => {
        const ripple = document.createElement("span");
        const rect = loginBtn.getBoundingClientRect();

        const size = Math.max(rect.width, rect.height);
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;

        ripple.classList.add("ripple");
        ripple.style.width = `${size}px`;
        ripple.style.height = `${size}px`;
        ripple.style.left = `${x}px`;
        ripple.style.top = `${y}px`;

        loginBtn.appendChild(ripple);

        setTimeout(() => {
            ripple.remove();
        }, 600);
    });
}

/* =========================
   Glow que sigue al cursor
   ========================= */

function iniciarCursorGlow() {
    const cursorGlow = document.getElementById("cursor-glow");

    if (!cursorGlow) return;

    document.addEventListener("mousemove", (e) => {
        cursorGlow.style.left = `${e.clientX}px`;
        cursorGlow.style.top = `${e.clientY}px`;
    });
}

/* =========================
   Movimiento suave de tarjeta
   Compatible con:
   .login-card
   .tarjeta-login
   ========================= */

function iniciarLoginCardMotion() {
    const loginCard =
        document.querySelector(".login-card") ||
        document.querySelector(".tarjeta-login");

    if (!loginCard) return;

    loginCard.addEventListener("mousemove", (e) => {
        const rect = loginCard.getBoundingClientRect();

        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const rotateX = ((y / rect.height) - 0.5) * -6;
        const rotateY = ((x / rect.width) - 0.5) * 6;

        loginCard.style.transform =
            `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
    });

    loginCard.addEventListener("mouseleave", () => {
        loginCard.style.transform =
            "perspective(1000px) rotateX(0deg) rotateY(0deg)";
    });
}

/* =========================
   Modo claro / oscuro
   ========================= */

function iniciarThemeToggle() {
    const themeBtn = document.querySelector(".theme-btn");
    const themeIcon = themeBtn?.querySelector("i");

    if (!themeBtn || !themeIcon) return;

    const temaGuardado = localStorage.getItem("vinova-theme");

    if (temaGuardado === "light") {
        document.body.classList.add("light-mode");
        themeIcon.classList.remove("fa-moon");
        themeIcon.classList.add("fa-sun");
    }

    themeBtn.addEventListener("click", () => {
        document.body.classList.toggle("light-mode");

        const modoClaroActivo = document.body.classList.contains("light-mode");

        themeIcon.classList.toggle("fa-moon", !modoClaroActivo);
        themeIcon.classList.toggle("fa-sun", modoClaroActivo);

        localStorage.setItem(
            "vinova-theme",
            modoClaroActivo ? "light" : "dark"
        );
    });
}

/* =========================
   Exponer funciones para onclick del HTML
   ========================= */

window.abrirModal = abrirModal;
window.cerrarModal = cerrarModal;

window.abrirRegistro = abrirRegistro;
window.cerrarRegistro = cerrarRegistro;

window.abrirSoporte = abrirSoporte;
window.cerrarSoporte = cerrarSoporte;

window.abrirContacto = abrirContacto;
window.cerrarContacto = cerrarContacto;

window.abrirNosotros = abrirNosotros;
window.cerrarNosotros = cerrarNosotros;

window.togglePassword = togglePassword;