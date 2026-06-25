
        // ================= RECUPERAR CONTRASEÑA =================

        function abrirModal() {

            document.getElementById("modal").style.display = "flex";

        }

        function cerrarModal() {

            document.getElementById("modal").style.display = "none";

        }

        // ================= REGISTRO =================

        function abrirRegistro() {

            document.getElementById("modal-registro").style.display = "flex";

        }

        function cerrarRegistro() {

            document.getElementById("modal-registro").style.display = "none";

        }

        // ================= SOPORTE =================

        function abrirSoporte() {

            document.getElementById("modal-soporte").style.display = "flex";

        }

        function cerrarSoporte() {

            document.getElementById("modal-soporte").style.display = "none";

        }

        // ================= CONTACTO =================

        function abrirContacto() {

            document.getElementById("modal-contacto").style.display = "flex";

        }

        function cerrarContacto() {

            document.getElementById("modal-contacto").style.display = "none";

        }

        // ================= SOBRE NOSOTROS =================

        function abrirNosotros() {

            document.getElementById("modal-nosotros").style.display = "flex";

        }

        function cerrarNosotros() {

            document.getElementById("modal-nosotros").style.display = "none";

        }

        // ================= MOSTRAR PASSWORD =================

        function togglePassword(){

            const input =
            document.getElementById("password");

            const icon =
            document.querySelector(".toggle-pass i");

            if(input.type === "password"){

                input.type = "text";

                icon.classList.remove("fa-eye");
                icon.classList.add("fa-eye-slash");

            }else{

                input.type = "password";

                icon.classList.remove("fa-eye-slash");
                icon.classList.add("fa-eye");

            }
        }

        // ================= CURSOR GLOW =================

        const glow = document.getElementById("cursor-glow");

        if(glow){

            document.addEventListener("mousemove", (e) => {

                glow.style.left = e.clientX + "px";
                glow.style.top = e.clientY + "px";

            });

        }
        // ================= CERRAR MODALES AFUERA =================

        window.addEventListener("click", (e) => {

            const modales = document.querySelectorAll(".modal");

            modales.forEach(modal => {

                if(e.target === modal){

                    modal.style.display = "none";

                }

            });

        });