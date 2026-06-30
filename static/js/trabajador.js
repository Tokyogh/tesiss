document.addEventListener("DOMContentLoaded", () => {
    initWorkerIcons();
    initWorkerSections();
    initWorkerSearch();
    initWorkerCopyButtons();
    initWorkerConfirmForms();
    initWorkerDisabledActions();
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

function initWorkerDoubleSubmitGuard() {
    const forms = document.querySelectorAll("form");

    forms.forEach((form) => {
        form.addEventListener("submit", () => {
            const submitButton = form.querySelector('button[type="submit"]');

            if (!submitButton) return;

            submitButton.disabled = true;
            submitButton.dataset.originalText = submitButton.textContent.trim();
            submitButton.textContent = "Procesando...";
        });
    });
}
