# Conciliación SIRE (RVIE) vs Bizlinks

Compara el registro de ventas del SIRE (archivo) contra los comprobantes de Bizlinks (BD PostgreSQL)
y guarda el historial. Flet web + worker en segundo plano con cola pgmq.

## Desarrollo

```bash
cp .env.example .env                              # HIST_DSN, BIZLINKS_DSN y claves
docker compose build
docker compose run --rm web python -m app.migrar   # crea/actualiza el esquema en HIST_DSN
docker compose up -d                              # bizlinks_dev (simulada), web, worker
```

- BD de historial: PostgreSQL externo (`HIST_DSN`), hoy `192.168.10.146/sire`. No hay contenedor de BD.
- App: **http://192.168.10.146** (puerto 80, nginx), en esta PC y desde la red. Por `:8550` directo
  funciona todo menos el botón de copiar (ver "Portapapeles por http").
- Pruebas: `docker compose run --rm web python -m unittest discover -s tests -t .`
  (las de la cola contra la BD necesitan `-e PRUEBAS_BD=1`; usan una cola propia y la borran al terminar)
- Tras cambiar código Python: `docker compose restart web worker`

## Portapapeles por http

Por `http://IP` el navegador no ofrece la API del portapapeles (solo existe en https o localhost) y
Flet/Flutter no tiene otra forma de copiar. nginx inserta `docker/nginx/portapapeles.js` en la página,
que copia con `document.execCommand('copy')`. Así funcionan el botón de copiar y Ctrl+C sobre texto
seleccionado. Pegar *dentro* de la app (Ctrl+V en un campo) no funciona por http; pegar en Excel, el Bloc de
notas, etc. sí.

## Producción (Ubuntu)

1. En `.env`, `BIZLINKS_DSN` apunta a la BD real de Bizlinks con un usuario de solo lectura.
2. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
3. La app queda en `http://<IP del servidor>` (puerto 80).

## Estructura

- `app/nucleo/`: común a todos los procesos (BD, lector SIRE, cola, UI de empresas y trabajos).
- `app/procesos/comparacion/`: el proceso de esta etapa (motor, manejador del worker, vistas).
- Nuevo proceso: crear `app/procesos/<nombre>/`, registrarlo en `app/procesos/__init__.py`,
  y agregar `sql/00N_<nombre>.sql` (tablas + `pgmq.create('<cola>')` + fila en `nucleo.proceso`).

## Migraciones

`python -m app.migrar` aplica en orden los `sql/*.sql` que falten y los registra en
`public.migracion_aplicada` (`--estado` solo lista). Un script ya aplicado no se vuelve a ejecutar:
los cambios van en un archivo nuevo `sql/00N_xxx.sql`. `000_pgmq.sql` es pgmq v1.8.0 en su versión
solo-SQL (el servidor no tiene la extensión).

## Fuentes de datos

**Cruce por CAR SUNAT** (27 caracteres: RUC 11 + tipo 2 + serie 4 + número con ceros 10). El SIRE lo trae
en la columna "CAR SUNAT" y cada fila se valida contra su RUC/tipo/serie/número (si no corresponde, la fila
se reporta como error). Bizlinks no lo guarda: se arma con los mismos datos de `spe_einvoiceheader`.

- **SIRE**: CSV del RVIE exportado de SUNAT (`LE<RUC><AAAAMM>00140400...EXP2.csv`), también ZIP/TXT/XLSX.
  Los anulados (`Est. Comp` = 2) no comparan montos. En notas de crédito la base e IGV suman
  "Dscto BI" / "Dscto IGV / IPM", donde el SIRE suele registrar el importe.
- **Bizlinks** (backup restaurado en `192.168.10.146/BIZLINKS_PROD21`; producción es
  `192.168.0.24/BIZLINKS_PROD21`; la conexión es siempre de solo lectura): montos y fecha de
  `spe_einvoiceheader` (columnas varchar; `bl_xml` de `spe_einvoice_response` viene vacío en parte de los
  comprobantes, por eso no se usa) y estado de `spe_einvoice_response.bl_estadoproceso`, clasificado en
  `app/nucleo/estados_ose.py` (AC_03 aceptado, RC_05 rechazado, AN_04 anulado; SIGNED, PE_02, PE_09 y
  ED_06 sin respuesta final). `bl_estadoregistro` no se usa. Consulta en
  `app/nucleo/db/consultas/bizlinks_comprobantes.sql`.
- BD simulada de Bizlinks para pruebas: `docker compose --profile simulado up -d bizlinks_dev` y
  apuntar `BIZLINKS_DSN` a `bizlinks_dev`.

## Periodos, sustento y cierre

- **Cabecera** `comparacion.periodo`: una por empresa + periodo. Cada carga del SIRE que termina bien pasa a
  ser la vigente y borra el detalle (`comparacion.detalle` / `totales`) de las cargas anteriores del periodo.
  `nucleo.trabajo`, `comparacion.resumen` y el archivo cargado se conservan como historial de cargas.
- **Requieren sustento** (`detalle.requiere_sustento`): con diferencia, solo SIRE, solo Bizlinks (salvo
  rechazados por SUNAT, que se sustentan solos con motivo `RECHAZADO_SUNAT`) e IGV observado.
- **Sustento** `comparacion.sustento`, por CAR: Pendiente / Sustentado / En corrección, con motivo
  (`comparacion.motivo_sustento`) y comentario obligatorios salvo en Pendiente. Sobrevive a las recargas;
  cada cambio queda en `comparacion.sustento_historial`.
- **Cierre**: solo cuando no queda ningún comprobante que requiera sustento y no esté Sustentado (En
  corrección también impide cerrar). Cerrado no admite cargas ni cambios de sustento; reabrir pide motivo.
  Cargas, cierres y reaperturas quedan en `comparacion.periodo_evento` (Bitácora).
- Aún no hay inicio de sesión: el usuario se registra como `web <IP del navegador>`.

## Pendiente

- Resúmenes diarios (RC) y comunicaciones de baja (RA): tablas `spe_summary*` y `spe_cancel*`.
- Inicio de sesión y roles (quién puede sustentar, cerrar y reabrir).
