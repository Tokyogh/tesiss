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
