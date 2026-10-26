-- Comprobantes solo en Bizlinks que aún no tienen respuesta final de SUNAT
-- (SIGNED, PE_02, PE_09, ED_06): pueden no figurar todavía en el SIRE.

ALTER TABLE comparacion.resumen
    ADD COLUMN IF NOT EXISTS solo_bizlinks_pendientes integer NOT NULL DEFAULT 0;
