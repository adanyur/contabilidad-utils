-- Comprobantes anulados: en el SIRE (Est. Comp = 2) figuran con montos en cero,
-- por eso solo se valida que existan y se deja registrado que estaban anulados.

ALTER TABLE comparacion.detalle
    ADD COLUMN IF NOT EXISTS sire_anulado boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS biz_anulado  boolean NOT NULL DEFAULT false;
