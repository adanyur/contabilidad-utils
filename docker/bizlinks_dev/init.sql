-- SOLO DESARROLLO: tabla spe_einvoice_response de Bizlinks con su DDL real.
-- El estado sale de esta tabla; montos y fecha de spe_einvoiceheader.

CREATE TABLE public.spe_einvoice_response (
	tipodocumentoemisor varchar(1) NOT NULL,
	numerodocumentoemisor varchar(20) NOT NULL,
	tipodocumento varchar(2) NOT NULL,
	serienumero varchar(13) NOT NULL,
	bl_estadoregistro varchar(1) NULL,
	bl_estadoproceso varchar(40) NULL,
	bl_mensaje varchar(4000) NULL,
	bl_mensajesunat varchar(4000) NULL,
	bl_firma varchar(4000) NULL,
	bl_hashfirma varchar(4000) NULL,
	bl_url_cdr varchar(4000) NULL,
	bl_url_pdf varchar(4000) NULL,
	bl_url_ubl varchar(4000) NULL,
	bl_cdr bytea NULL,
	bl_pdf bytea NULL,
	bl_xml bytea NULL,
	bl_ubl bytea NULL,
	bl_fecharespuestasunat varchar(50) NULL,
	bl_fechaenviosunat varchar(50) NULL,
	bl_ticket varchar(15) NULL,
	process_state varchar(20) NULL,
	running int4 DEFAULT 0 NULL,
	reintento int4 DEFAULT 0 NULL,
	next_try int8 NULL,
	origen varchar(1) NULL,
	pdf_state varchar(20) NULL,
	xml_state varchar(20) NULL,
	ubl_state varchar(20) NULL,
	cdr_state varchar(20) NULL,
	attachment_state varchar(20) NULL,
	bl_xml_rsp text NULL,
	CONSTRAINT spe_einvoice_response_pkey PRIMARY KEY (tipodocumentoemisor, numerodocumentoemisor, tipodocumento, serienumero)
);
CREATE INDEX index_einvoice_response ON public.spe_einvoice_response USING btree (numerodocumentoemisor, serienumero, tipodocumento, tipodocumentoemisor, running);

-- Cabecera de comprobantes (subconjunto de las 290 columnas reales, todas varchar como en producción).
-- De aquí salen montos y fecha de emisión.
CREATE TABLE public.spe_einvoiceheader (
	tipodocumentoemisor varchar(1) NOT NULL,
	numerodocumentoemisor varchar(20) NOT NULL,
	tipodocumento varchar(2) NOT NULL,
	serienumero varchar(13) NOT NULL,
	fechaemision varchar(10),
	tipomoneda varchar(3),
	numerodocumentoadquiriente varchar(20),
	totalvalorventanetoopgravadas varchar(20),
	totaligv varchar(20),
	totalventa varchar(20),
	CONSTRAINT spe_einvoiceheader_pkey PRIMARY KEY (numerodocumentoemisor, serienumero, tipodocumento, tipodocumentoemisor)
);

-- Datos de ejemplo para la empresa 20100000001, periodo 2026-09.
-- Combinados con tests/datos/sire_rvie_ejemplo.txt generan los cuatro estados.
CREATE TEMP TABLE ejemplo AS
SELECT * FROM (VALUES
    ('01', 'F001-00000001', '2026-09-01', 'PEN', '20500000001', '100.00', '18.00', '118.00', 'SIGNED/AC_03', NULL),   -- coincide
    ('01', 'F001-00000002', '2026-09-02', 'PEN', '20500000002', '200.00', '36.00', '236.00', 'SIGNED/AC_03', NULL),   -- coincide
    ('01', 'F001-00000003', '2026-09-03', 'PEN', '20500000003', '300.00', '54.00', '354.00', 'SIGNED/AC_03', NULL),   -- diferencia de monto
    ('03', 'B001-00000010', '2026-09-04', 'PEN', '10456789012', '50.00', '9.00', '59.00', 'SIGNED/ AC_03', NULL),     -- coincide (estado con espacio)
    ('01', 'F001-00000005', '2026-09-06', 'USD', '20500000005', '1000.00', '180.00', '1180.00', 'SIGNED/AC_03', NULL), -- solo Bizlinks
    ('07', 'FC01-00000001', '2026-09-10', 'PEN', '20500000001', '10.00', '1.80', '11.80', 'SIGNED/AC_03', NULL),      -- coincide (NC)
    ('01', 'F001-00000006', '2026-09-12', 'PEN', '20500000006', '297.75', '53.59', '351.34', 'SIGNED/RC_05',
     '{"codigo":"3270","mensaje":"El precio unitario de la operación que está informando difiere de los cálculos realizados en base a la información remitida - [1]"}')
                                                                                                                -- solo Bizlinks, rechazado por SUNAT
) AS d(tipo, sn, fecha, moneda, doc, gravada, igv, total, estado, mensaje);

INSERT INTO spe_einvoiceheader
    (tipodocumentoemisor, numerodocumentoemisor, tipodocumento, serienumero, fechaemision, tipomoneda,
     numerodocumentoadquiriente, totalvalorventanetoopgravadas, totaligv, totalventa)
SELECT '6', '20100000001', tipo, sn, fecha, moneda, doc, gravada, igv, total FROM ejemplo;

INSERT INTO spe_einvoice_response
    (tipodocumentoemisor, numerodocumentoemisor, tipodocumento, serienumero, bl_estadoproceso, bl_mensajesunat,
     bl_fecharespuestasunat, process_state)
SELECT '6', '20100000001', tipo, sn, estado, mensaje, fecha, '_3_COMPLETED' FROM ejemplo;

-- Usuario de solo lectura que usa la aplicación
CREATE ROLE bizlinks_lectura LOGIN PASSWORD 'lectura_dev';
GRANT CONNECT ON DATABASE bizlinks TO bizlinks_lectura;
GRANT USAGE ON SCHEMA public TO bizlinks_lectura;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO bizlinks_lectura;
