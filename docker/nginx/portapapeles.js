// nginx lo inyecta en la página de Flet. Por http://IP el navegador no ofrece navigator.clipboard
// (solo existe en https o localhost) y Flutter no tiene otro modo de copiar: el botón de copiar y
// Ctrl+C no hacían nada. Aquí se copia con document.execCommand('copy'), que sí funciona por http
// mientras venga de un clic o una tecla del usuario.
(function () {
  if (window.isSecureContext || navigator.clipboard) return;
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      writeText: function (texto) {
        return new Promise(function (ok, falla) {
          var area = document.createElement("textarea");
          area.value = texto;
          area.setAttribute("readonly", "");
          area.style.cssText = "position:fixed;top:0;left:0;opacity:0";
          document.body.appendChild(area);
          area.select();
          var copiado = document.execCommand("copy");
          area.remove();
          copiado ? ok() : falla(new Error("No se pudo copiar"));
        });
      },
      // Leer el portapapeles por http no es posible; la app no lo usa
      readText: function () {
        return Promise.reject(new Error("Portapapeles no disponible por http"));
      },
    },
  });
})();
