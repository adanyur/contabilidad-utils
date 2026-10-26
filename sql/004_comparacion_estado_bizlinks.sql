-- Estado del comprobante en Bizlinks (bl_estadoproceso) y respuesta de SUNAT.
-- Un comprobante rechazado por SUNAT no debería figurar en el SIRE.

ALTER TABLE comparacion.detalle
    ADD COLUMN IF NOT EXISTS biz_estado        varchar(40),
    ADD COLUMN IF NOT EXISTS biz_mensaje_sunat text;

ALTER TABLE comparacion.resumen
    ADD COLUMN IF NOT EXISTS solo_bizlinks_rechazados integer NOT NULL DEFAULT 0;
