document.addEventListener("DOMContentLoaded", () => {
    initVinovaArticlePanels();
    initVinovaHiddenVehiclePanel();
    initVinovaHiddenArticlePanels();
    initVinovaArticleFileInputs();
    initVinovaArticleInvoiceBuilders();
    initVinovaArticleCatalogFilters();
});

function vinovaArticleNormalize(text) {
    return String(text || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim();
}

function vinovaMoney(value) {
    const number = Number(value || 0);
    return `$${number.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function vinovaStaticUrl(path) {
    const clean = String(path || "").replace(/^\/+/, "");
    return clean ? `/static/${clean}` : "";
}

function vinovaGetCsrf() {
    const input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value : "";
}

function initVinovaArticlePanels() {
    document.querySelectorAll("[data-articulos-panel]").forEach((panel) => {
        const apiUrl = panel.dataset.articulosApi || "/articulos/api/gestion";
        const list = panel.querySelector("[data-articulos-panel-list]");
        const searchInput = panel.querySelector("[data-articulos-panel-search]");
        const form = panel.querySelector("[data-articulo-form]");
        const resetButton = panel.querySelector("[data-articulo-reset]");
        const stats = panel.querySelectorAll("[data-articulo-stat]");
        const origen = panel.dataset.origen || "admin";
        let articulos = [];

        if (!list) return;

        function updateStats(payloadStats) {
            stats.forEach((stat) => {
                const key = stat.dataset.articuloStat;
                stat.textContent = payloadStats && key in payloadStats ? payloadStats[key] : "0";
            });
        }

        function renderList() {
            const search = vinovaArticleNormalize(searchInput ? searchInput.value : "");
            const filtered = articulos.filter((articulo) => {
                if (!search) return true;
                return vinovaArticleNormalize([
                    articulo.codigo_articulo,
                    articulo.nombre,
                    articulo.categoria,
                    articulo.marca,
                    articulo.estado,
                    articulo.proveedor
                ].join(" ")).includes(search);
            });

            if (!filtered.length) {
                list.innerHTML = `
                    <div class="articulos-empty">
                        <i data-lucide="package-search"></i>
                        <h3>Sin artículos</h3>
                        <p>No hay artículos que coincidan con la búsqueda actual.</p>
                    </div>
                `;
                if (window.lucide) window.lucide.createIcons();
                return;
            }

            list.innerHTML = filtered.map((articulo) => {
                const img = articulo.imagen_url || "";
                const stock = Number(articulo.stock || 0);
                const minimo = Number(articulo.stock_minimo || 0);
                const lowStock = minimo > 0 && stock <= minimo;
                const activo = Number(articulo.activo || 0) === 1;
                const estadoClass = activo ? "active" : "inactive";
                const stockClass = lowStock ? "warning" : (stock > 0 ? "active" : "sold");
                const safeJson = encodeURIComponent(JSON.stringify(articulo));
                return `
                    <article class="articulo-row" data-articulo-row data-articulo-json="${safeJson}">
                        <div class="articulo-thumb">
                            ${img ? `<img src="${img}" alt="${articulo.nombre || 'Artículo'}">` : `<i data-lucide="package"></i>`}
                        </div>
                        <div class="articulo-info">
                            <div class="articulo-heading">
                                <div>
                                    <h3>${articulo.nombre || 'Artículo'}</h3>
                                    <p>${articulo.codigo_articulo || 'Sin código'} · ${articulo.categoria || 'Otros'}${articulo.marca ? ' · ' + articulo.marca : ''}</p>
                                </div>
                                <strong>${vinovaMoney(articulo.precio)}</strong>
                            </div>
                            <div class="articulo-meta">
                                <span class="admin-status ${estadoClass}">${activo ? 'Visible' : 'Oculto'}</span>
                                <span class="admin-status ${stockClass}">${stock.toLocaleString('es-EC')} ${articulo.unidad || 'Unidad'} en stock</span>
                                <span>${Number(articulo.unidades_vendidas || 0).toLocaleString('es-EC')} vendidas</span>
                                ${lowStock ? `<span class="admin-status warning">Stock bajo</span>` : ''}
                            </div>
                            ${articulo.descripcion ? `<p class="articulo-description">${articulo.descripcion}</p>` : ''}
                        </div>
                        <div class="articulo-actions">
                            <button type="button" class="articulo-mini-btn" data-articulo-edit>Editar</button>
                            <button type="button" class="articulo-mini-btn ${activo ? 'danger' : 'success'}" data-articulo-toggle>${activo ? 'Ocultar' : 'Activar'}</button>
                            <button type="button" class="articulo-mini-btn danger" data-articulo-archive>Eliminar</button>
                        </div>
                    </article>
                `;
            }).join("");

            list.querySelectorAll("[data-articulo-edit]").forEach((button) => {
                button.addEventListener("click", () => {
                    const row = button.closest("[data-articulo-row]");
                    const articulo = JSON.parse(decodeURIComponent(row.dataset.articuloJson || "{}"));
                    fillForm(articulo);
                });
            });

            list.querySelectorAll("[data-articulo-toggle]").forEach((button) => {
                button.addEventListener("click", async () => {
                    const row = button.closest("[data-articulo-row]");
                    const articulo = JSON.parse(decodeURIComponent(row.dataset.articuloJson || "{}"));
                    await postArticleAction(`/articulos/${articulo.id}/estado`, { origen });
                    await loadArticles();
                });
            });

            list.querySelectorAll("[data-articulo-archive]").forEach((button) => {
                button.addEventListener("click", async () => {
                    const row = button.closest("[data-articulo-row]");
                    const articulo = JSON.parse(decodeURIComponent(row.dataset.articuloJson || "{}"));
                    if (!confirm(`¿Eliminar/archivar el artículo ${articulo.nombre}?`)) return;
                    await postArticleAction(`/articulos/${articulo.id}/archivar`, { origen, motivo: "Archivado desde panel" });
                    await loadArticles();
                });
            });

            if (window.lucide) window.lucide.createIcons();
        }

        async function postArticleAction(url, values) {
            const body = new URLSearchParams();
            body.set("csrf_token", vinovaGetCsrf());
            Object.entries(values || {}).forEach(([key, value]) => body.set(key, value));
            const response = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body
            });
            const data = await response.json().catch(() => ({ ok: false }));
            if (!data.ok) {
                alert(data.error || "No se pudo completar la acción.");
            }
            return data;
        }

        function fillForm(articulo) {
            if (!form) return;
            form.querySelector('[name="articulo_id"]').value = articulo.id || "";
            form.querySelector('[name="codigo_articulo"]').value = articulo.codigo_articulo || "";
            form.querySelector('[name="nombre"]').value = articulo.nombre || "";
            form.querySelector('[name="categoria"]').value = articulo.categoria || "Otros";
            form.querySelector('[name="marca"]').value = articulo.marca || "";
            form.querySelector('[name="proveedor"]').value = articulo.proveedor || "";
            form.querySelector('[name="precio"]').value = articulo.precio || 0;
            form.querySelector('[name="costo"]').value = articulo.costo || 0;
            form.querySelector('[name="stock"]').value = articulo.stock || 0;
            form.querySelector('[name="stock_minimo"]').value = articulo.stock_minimo || 0;
            form.querySelector('[name="unidad"]').value = articulo.unidad || "Unidad";
            form.querySelector('[name="estado"]').value = articulo.estado || "Disponible";
            form.querySelector('[name="descripcion"]').value = articulo.descripcion || "";
            const activo = form.querySelector('[name="activo"]');
            if (activo) activo.checked = Number(articulo.activo || 0) === 1;
            const title = panel.querySelector("[data-articulo-form-title]");
            if (title) title.textContent = "Editar artículo";
            form.scrollIntoView({ behavior: "smooth", block: "start" });
        }

        function resetForm() {
            if (!form) return;
            form.reset();
            form.querySelector('[name="articulo_id"]').value = "";
            const activo = form.querySelector('[name="activo"]');
            if (activo) activo.checked = true;
            form.querySelectorAll("[data-articulo-file-name]").forEach((label) => {
                label.textContent = "Selecciona PNG, JPG o WEBP. Se guarda en static/img/articulos/.";
            });
            const title = panel.querySelector("[data-articulo-form-title]");
            if (title) title.textContent = "Agregar artículo";
        }

        async function loadArticles() {
            list.innerHTML = `<div class="articulos-loading">Cargando inventario...</div>`;
            try {
                const response = await fetch(apiUrl, { headers: { "Accept": "application/json" } });
                const data = await response.json();
                if (!data.ok) throw new Error(data.error || "No se pudo cargar el inventario.");
                articulos = data.articulos || [];
                updateStats(data.stats || {});
                renderList();
            } catch (error) {
                list.innerHTML = `
                    <div class="articulos-empty error">
                        <i data-lucide="triangle-alert"></i>
                        <h3>No se pudo cargar artículos</h3>
                        <p>${error.message || 'Ejecuta la migración de artículos.'}</p>
                    </div>
                `;
                if (window.lucide) window.lucide.createIcons();
            }
        }

        if (searchInput) searchInput.addEventListener("input", renderList);
        if (resetButton) resetButton.addEventListener("click", resetForm);
        loadArticles();
    });
}

function initVinovaHiddenVehiclePanel() {
    document.querySelectorAll("[data-vehiculos-ocultos-panel]").forEach((panel) => {
        const list = panel.querySelector("[data-vehiculos-ocultos-list]");
        const apiUrl = panel.dataset.vehiculosOcultosApi || "/inventario/vehiculos/ocultos/api";
        const csrf = panel.dataset.csrf || vinovaGetCsrf();
        const origen = panel.dataset.origen || "admin";
        if (!list) return;

        async function loadVehicles() {
            try {
                const response = await fetch(apiUrl, { headers: { "Accept": "application/json" } });
                const data = await response.json();
                if (!data.ok) throw new Error(data.error || "No se pudo cargar inventario oculto.");
                renderVehicles(data.vehiculos || []);
            } catch (error) {
                list.innerHTML = `<div class="articulos-empty error"><h3>No se pudo cargar</h3><p>${error.message}</p></div>`;
            }
        }

        function vehicleEditHref(vehiculo) {
            if (origen === "trabajador") return `/trabajador#trabajador-vehiculos`;
            return `/admin/vehiculos?editar=${vehiculo.id}#admin-vehiculos`;
        }

        function vehicleToggleAction(vehiculo) {
            return `/inventario/vehiculos/${vehiculo.id}/activar`;
        }

        function vehicleArchiveAction(vehiculo) {
            return origen === "trabajador" ? `/trabajador/vehiculos/${vehiculo.id}/archivar` : `/admin/vehiculos/${vehiculo.id}/archivar`;
        }

        function renderVehicles(vehiculos) {
            if (!vehiculos.length) {
                list.innerHTML = `<div class="articulos-empty"><i data-lucide="eye"></i><h3>Sin vehículos ocultos</h3><p>Cuando ocultes vehículos del catálogo aparecerán aquí.</p></div>`;
                if (window.lucide) window.lucide.createIcons();
                return;
            }

            list.innerHTML = vehiculos.map((vehiculo) => `
                <article class="articulo-row vehiculo-oculto-row">
                    <div class="articulo-thumb">
                        ${vehiculo.imagen_url ? `<img src="${vehiculo.imagen_url}" alt="${vehiculo.marca} ${vehiculo.modelo}">` : `<i data-lucide="car-front"></i>`}
                    </div>
                    <div class="articulo-info">
                        <div class="articulo-heading">
                            <div>
                                <h3>${vehiculo.marca || ''} ${vehiculo.modelo || ''}</h3>
                                <p>${vehiculo.codigo_catalogo || 'Sin código'} · ${vehiculo.anio || ''} · ${vehiculo.tipo_vehiculo || 'Vehículo'}</p>
                            </div>
                            <strong>${vinovaMoney(vehiculo.precio)}</strong>
                        </div>
                        <div class="articulo-meta">
                            <span class="admin-status inactive">Oculto</span>
                            <span>${Number(vehiculo.kilometraje || 0).toLocaleString('es-EC')} km</span>
                            <span>${vehiculo.estado || 'Disponible'}</span>
                        </div>
                    </div>
                    <div class="articulo-actions">
                        <a class="articulo-mini-btn" href="${vehicleEditHref(vehiculo)}">Gestionar</a>
                        <form action="${vehicleToggleAction(vehiculo)}" method="POST">
                            <input type="hidden" name="csrf_token" value="${csrf}">
                            <input type="hidden" name="origen" value="${origen}">
                            <button type="submit" class="articulo-mini-btn success">Activar</button>
                        </form>
                        <form action="${vehicleArchiveAction(vehiculo)}" method="POST" onsubmit="return confirm('¿Archivar esta unidad oculta?')">
                            <input type="hidden" name="csrf_token" value="${csrf}">
                            <input type="hidden" name="motivo_archivado" value="Archivado desde inventario oculto">
                            <button type="submit" class="articulo-mini-btn danger">Archivar</button>
                        </form>
                    </div>
                </article>
            `).join("");
            if (window.lucide) window.lucide.createIcons();
        }

        loadVehicles();
    });
}

function initVinovaHiddenArticlePanels() {
    document.querySelectorAll("[data-articulos-ocultos-panel]").forEach((panel) => {
        const list = panel.querySelector("[data-articulos-ocultos-list]");
        const apiUrl = panel.dataset.articulosOcultosApi || "/articulos/api/gestion";
        const origen = panel.dataset.origen || "admin";
        if (!list) return;

        async function postArticleAction(url, values) {
            const body = new URLSearchParams();
            body.set("csrf_token", vinovaGetCsrf());
            Object.entries(values || {}).forEach(([key, value]) => body.set(key, value));
            const response = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body
            });
            const data = await response.json().catch(() => ({ ok: false }));
            if (!data.ok) alert(data.error || "No se pudo completar la acción.");
            return data;
        }

        async function loadHiddenArticles() {
            list.innerHTML = `<div class="articulos-loading">Cargando artículos ocultos...</div>`;
            try {
                const response = await fetch(apiUrl, { headers: { "Accept": "application/json" } });
                const data = await response.json();
                if (!data.ok) throw new Error(data.error || "No se pudo cargar artículos ocultos.");
                renderHiddenArticles((data.articulos || []).filter((articulo) => Number(articulo.activo || 0) === 0 && Number(articulo.archivado || 0) === 0));
            } catch (error) {
                list.innerHTML = `<div class="articulos-empty error"><h3>No se pudo cargar</h3><p>${error.message}</p></div>`;
            }
        }

        function renderHiddenArticles(articulos) {
            if (!articulos.length) {
                list.innerHTML = `<div class="articulos-empty"><i data-lucide="package-check"></i><h3>Sin artículos ocultos</h3><p>Cuando ocultes artículos del catálogo aparecerán aquí.</p></div>`;
                if (window.lucide) window.lucide.createIcons();
                return;
            }

            list.innerHTML = articulos.map((articulo) => `
                <article class="articulo-row">
                    <div class="articulo-thumb">
                        ${articulo.imagen_url ? `<img src="${articulo.imagen_url}" alt="${articulo.nombre || 'Artículo'}">` : `<i data-lucide="package"></i>`}
                    </div>
                    <div class="articulo-info">
                        <div class="articulo-heading">
                            <div>
                                <h3>${articulo.nombre || 'Artículo'}</h3>
                                <p>${articulo.codigo_articulo || 'Sin código'} · ${articulo.categoria || 'Otros'}${articulo.marca ? ' · ' + articulo.marca : ''}</p>
                            </div>
                            <strong>${vinovaMoney(articulo.precio)}</strong>
                        </div>
                        <div class="articulo-meta">
                            <span class="admin-status inactive">Oculto</span>
                            <span>${Number(articulo.stock || 0).toLocaleString('es-EC')} ${articulo.unidad || 'Unidad'} en stock</span>
                            <span>${Number(articulo.unidades_vendidas || 0).toLocaleString('es-EC')} vendidas</span>
                        </div>
                    </div>
                    <div class="articulo-actions">
                        <a class="articulo-mini-btn" href="#${origen === 'trabajador' ? 'trabajador' : 'admin'}-articulos">Gestionar</a>
                        <button type="button" class="articulo-mini-btn success" data-hidden-articulo-activate="${articulo.id}">Activar</button>
                        <button type="button" class="articulo-mini-btn danger" data-hidden-articulo-archive="${articulo.id}">Archivar</button>
                    </div>
                </article>
            `).join("");

            list.querySelectorAll("[data-hidden-articulo-activate]").forEach((button) => {
                button.addEventListener("click", async () => {
                    await postArticleAction(`/articulos/${button.dataset.hiddenArticuloActivate}/estado`, { origen });
                    await loadHiddenArticles();
                });
            });

            list.querySelectorAll("[data-hidden-articulo-archive]").forEach((button) => {
                button.addEventListener("click", async () => {
                    if (!confirm("¿Archivar este artículo oculto?")) return;
                    await postArticleAction(`/articulos/${button.dataset.hiddenArticuloArchive}/archivar`, { origen, motivo: "Archivado desde inventario oculto" });
                    await loadHiddenArticles();
                });
            });

            if (window.lucide) window.lucide.createIcons();
        }

        loadHiddenArticles();
    });
}

function initVinovaArticleFileInputs() {
    document.querySelectorAll(".articulo-file-field input[type='file']").forEach((input) => {
        const box = input.closest(".articulo-file-field");
        const label = box ? box.querySelector("[data-articulo-file-name]") : null;
        const defaultText = label ? label.textContent : "";

        input.addEventListener("change", () => {
            if (!label) return;
            const file = input.files && input.files[0];
            label.textContent = file ? `Imagen seleccionada: ${file.name}` : defaultText;
        });
    });
}

function initVinovaArticleInvoiceBuilders() {
    document.querySelectorAll("[data-articulo-factura-builder]").forEach((builder) => {
        const searchUrl = builder.dataset.articuloSearchUrl || "/articulos/buscar-factura";
        const input = builder.querySelector("[data-articulo-search-input]");
        const results = builder.querySelector("[data-articulo-results]");
        const selectedBox = builder.querySelector("[data-articulo-selected]");
        const subtotalLabel = builder.querySelector("[data-articulo-subtotal]");
        const clearButton = builder.querySelector("[data-articulo-clear]");
        const form = builder.closest("form");
        let selected = [];
        let timer = null;

        if (!input || !results || !selectedBox || !form) return;

        function updateTotals() {
            const subtotal = selected.reduce((sum, item) => sum + Number(item.cantidad || 0) * Number(item.precio || 0), 0);
            if (subtotalLabel) subtotalLabel.textContent = vinovaMoney(subtotal);
            const montoInput = form.querySelector('[name="monto"]');
            const conceptoInput = form.querySelector('[name="concepto"]');
            const descripcionInput = form.querySelector('[name="descripcion"]');
            const tipoInput = form.querySelector('[name="tipo_factura"]');

            if (selected.length && montoInput) montoInput.value = subtotal.toFixed(2);
            if (selected.length && conceptoInput && !conceptoInput.value.trim()) conceptoInput.value = "Venta de artículos VINOVA";
            if (selected.length && descripcionInput && !descripcionInput.value.trim()) {
                descripcionInput.value = selected.map((item) => `${item.nombre} x ${item.cantidad}`).join("; ");
            }
            if (selected.length && tipoInput) tipoInput.value = "Producto";
        }

        function renderSelected() {
            if (!selected.length) {
                selectedBox.innerHTML = `<div class="article-invoice-empty">Aún no seleccionas artículos del inventario.</div>`;
                updateTotals();
                return;
            }

            selectedBox.innerHTML = selected.map((item, index) => `
                <div class="article-invoice-row">
                    <input type="hidden" name="articulo_id[]" value="${item.id}">
                    <input type="hidden" name="articulo_cantidad[]" value="${item.cantidad}">
                    <strong>${item.nombre}</strong>
                    <span>${item.codigo || 'Sin código'} · ${vinovaMoney(item.precio)} · Stock: ${item.stock}</span>
                    <label>
                        Cantidad
                        <input type="number" min="1" step="1" max="${Math.floor(Number(item.stock || 1))}" value="${item.cantidad}" data-invoice-qty="${index}">
                    </label>
                    <b>${vinovaMoney(Number(item.precio) * Number(item.cantidad))}</b>
                    <button type="button" data-remove-invoice-item="${index}">Quitar</button>
                </div>
            `).join("");

            selectedBox.querySelectorAll("[data-invoice-qty]").forEach((qtyInput) => {
                qtyInput.addEventListener("input", () => {
                    const index = Number(qtyInput.dataset.invoiceQty);
                    const item = selected[index];
                    const max = Math.max(1, Math.floor(Number(item.stock || 1)));
                    let value = Math.max(1, Math.min(max, Number(qtyInput.value || 1)));
                    selected[index].cantidad = value;
                    renderSelected();
                });
            });

            selectedBox.querySelectorAll("[data-remove-invoice-item]").forEach((button) => {
                button.addEventListener("click", () => {
                    selected.splice(Number(button.dataset.removeInvoiceItem), 1);
                    renderSelected();
                });
            });

            updateTotals();
        }

        function addArticle(articulo) {
            const existing = selected.find((item) => Number(item.id) === Number(articulo.id));
            if (existing) {
                existing.cantidad = Math.min(Number(existing.cantidad || 1) + 1, Math.floor(Number(existing.stock || 1)));
            } else {
                selected.push({
                    id: articulo.id,
                    codigo: articulo.codigo_articulo,
                    nombre: articulo.nombre,
                    precio: Number(articulo.precio || 0),
                    stock: Number(articulo.stock || 0),
                    cantidad: 1
                });
            }
            results.hidden = true;
            input.value = "";
            renderSelected();
        }

        async function searchArticles(query) {
            if (!query || query.length < 2) {
                results.hidden = true;
                return;
            }

            const url = `${searchUrl}?q=${encodeURIComponent(query)}`;
            const response = await fetch(url, { headers: { "Accept": "application/json" } });
            const data = await response.json();

            if (!data.ok || !data.resultados || !data.resultados.length) {
                results.hidden = false;
                results.innerHTML = `<div class="article-result-empty">Sin artículos disponibles.</div>`;
                return;
            }

            results.hidden = false;
            results.innerHTML = data.resultados.map((articulo, index) => `
                <button type="button" class="article-result-item" data-article-result="${index}">
                    ${articulo.imagen_url ? `<img src="${articulo.imagen_url}" alt="${articulo.nombre}">` : `<i data-lucide="package"></i>`}
                    <span><strong>${articulo.nombre}</strong><small>${articulo.codigo_articulo} · ${articulo.categoria} · Stock: ${articulo.stock}</small></span>
                    <b>${vinovaMoney(articulo.precio)}</b>
                </button>
            `).join("");

            results.querySelectorAll("[data-article-result]").forEach((button) => {
                button.addEventListener("click", () => addArticle(data.resultados[Number(button.dataset.articleResult)]));
            });

            if (window.lucide) window.lucide.createIcons();
        }

        input.addEventListener("input", () => {
            window.clearTimeout(timer);
            timer = window.setTimeout(() => searchArticles(input.value.trim()), 320);
        });

        if (clearButton) {
            clearButton.addEventListener("click", () => {
                input.value = "";
                results.hidden = true;
                input.focus();
            });
        }

        renderSelected();
    });
}

function initVinovaArticleCatalogFilters() {
    document.querySelectorAll("[data-articulos-filter-form]").forEach((form) => {
        form.addEventListener("submit", () => {
            form.querySelectorAll("input, select").forEach((field) => {
                if (!field.name) return;
                if ((field.type === "checkbox" || field.type === "radio") && !field.checked) {
                    field.disabled = true;
                    return;
                }
                if (String(field.value || "").trim() === "") {
                    field.disabled = true;
                }
            });
        });
    });
}
