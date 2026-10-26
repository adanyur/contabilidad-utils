-- La comparación pasa a tener tres fases:
--   1. comprobante por comprobante (comparacion.detalle, ya existía)
--   2. totales por tipo de comprobante y moneda (comparacion.totales)
--   3. IGV calculado (base x tasa) frente al IGV del SIRE y de Bizlinks (columnas *_igv_calculado)

CREATE TABLE IF NOT EXISTS comparacion.totales (
    trabajo_id          bigint        NOT NULL REFERENCES nucleo.trabajo (id) ON DELETE CASCADE,
    tipo_cp             varchar(5)    NOT NULL,  -- 01, 03, 07, 08 o TOTAL
    moneda              char(3)       NOT NULL,
    sire_cantidad       integer       NOT NULL,
    sire_base           numeric(15,2) NOT NULL,
    sire_igv            numeric(15,2) NOT NULL,
    sire_total          numeric(15,2) NOT NULL,
    sire_igv_calculado  numeric(15,2) NOT NULL,
    biz_cantidad        integer       NOT NULL,
    biz_base            numeric(15,2) NOT NULL,
    biz_igv             numeric(15,2) NOT NULL,
    biz_total           numeric(15,2) NOT NULL,
    biz_igv_calculado   numeric(15,2) NOT NULL,
    diferencias         jsonb,
    PRIMARY KEY (trabajo_id, tipo_cp, moneda)
);

ALTER TABLE comparacion.detalle
    ADD COLUMN IF NOT EXISTS sire_igv_calculado numeric(15,2),
    ADD COLUMN IF NOT EXISTS biz_igv_calculado  numeric(15,2),
    ADD COLUMN IF NOT EXISTS igv_observado      boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS detalle_igv_observado_idx ON comparacion.detalle (trabajo_id) WHERE igv_observado;

-- fases = 1 en las comparaciones hechas antes de este cambio (no tienen totales ni verificación de IGV)
ALTER TABLE comparacion.resumen
    ADD COLUMN IF NOT EXISTS fases                     smallint NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS tasa_igv                  numeric(5,4),
    ADD COLUMN IF NOT EXISTS tolerancia_igv            numeric(8,2),
    ADD COLUMN IF NOT EXISTS igv_observados_sire       integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS igv_observados_bizlinks   integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS totales_excluidos_sire    integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS totales_excluidos_bizlinks integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS totales_con_diferencia    integer NOT NULL DEFAULT 0;
