-- Comprobantes emitidos en Bizlinks para un RUC y un periodo.
-- Debe devolver los alias: ruc, tipo_cp, serie, numero, fecha_emision, moneda, base_imponible, igv,
-- total, doc_receptor, estado_ose, mensaje_sunat.
--
-- Montos y fecha salen de la cabecera spe_einvoiceheader (no del XML bl_xml de spe_einvoice_response,
-- que viene vacío en parte de los comprobantes). Las columnas son varchar: fechaemision en AAAA-MM-DD,
-- por eso el filtro por periodo compara texto; los montos se convierten en Python (normalizador.monto).
-- base_imponible = operaciones gravadas, igual que "BI Gravada" del SIRE.
-- El estado viene de spe_einvoice_response.bl_estadoproceso (misma llave primaria).
SELECT h.numerodocumentoemisor              AS ruc,
       h.tipodocumento                      AS tipo_cp,
       split_part(h.serienumero, '-', 1)    AS serie,
       split_part(h.serienumero, '-', 2)    AS numero,
       h.fechaemision                       AS fecha_emision,
       h.tipomoneda                         AS moneda,
       h.totalvalorventanetoopgravadas      AS base_imponible,
       h.totaligv                           AS igv,
       h.totalventa                         AS total,
       h.numerodocumentoadquiriente         AS doc_receptor,
       r.bl_estadoproceso                   AS estado_ose,
       r.bl_mensajesunat                    AS mensaje_sunat
  FROM spe_einvoiceheader h
  LEFT JOIN spe_einvoice_response r
       USING (tipodocumentoemisor, numerodocumentoemisor, tipodocumento, serienumero)
 WHERE h.numerodocumentoemisor = %(ruc)s
   AND h.tipodocumentoemisor = '6'
   AND h.tipodocumento IN ('01', '03', '07', '08')
   AND h.fechaemision >= %(desde)s
   AND h.fechaemision <  %(hasta)s
