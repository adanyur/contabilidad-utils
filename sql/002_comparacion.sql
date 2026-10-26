-- Tablas propias del proceso de comparación SIRE (RVIE) vs Bizlinks.

CREATE SCHEMA IF NOT EXISTS comparacion;

-- Cola pgmq del proceso
SELECT pgmq.create('comparacion');

CREATE TABLE comparacion.resumen (
    trabajo_id      bigint  PRIMARY KEY REFERENCES nucleo.trabajo (id) ON DELETE CASCADE,
    total_sire      integer NOT NULL,
    total_bizlinks  integer NOT NULL,
    coinciden       integer NOT NULL,
    con_diferencia  integer NOT NULL,
    solo_sire       integer NOT NULL,
    solo_bizlinks   integer NOT NULL,
    filas_con_error integer NOT NULL DEFAULT 0,  -- filas del archivo SIRE que no se pudieron leer
    duplicados      integer NOT NULL DEFAULT 0   -- llaves repetidas dentro de un mismo origen
);

CREATE TABLE comparacion.detalle (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trabajo_id       bigint      NOT NULL REFERENCES nucleo.trabajo (id) ON DELETE CASCADE,
    tipo_cp          char(2)     NOT NULL,
    serie            varchar(20) NOT NULL,
    numero           bigint      NOT NULL,
    estado           varchar(15) NOT NULL
                     CHECK (estado IN ('COINCIDE', 'DIFERENCIA', 'SOLO_SIRE', 'SOLO_BIZLINKS')),
    sire_fecha       date,
    sire_moneda      char(3),
    sire_base        numeric(15,2),
    sire_igv         numeric(15,2),
    sire_total       numeric(15,2),
    sire_doc_receptor varchar(20),
    biz_fecha        date,
    biz_moneda       char(3),
    biz_base         numeric(15,2),
    biz_igv          numeric(15,2),
    biz_total        numeric(15,2),
    biz_doc_receptor varchar(20),
    diferencias      jsonb       -- {"campo": {"sire": ..., "bizlinks": ...}}
);

CREATE INDEX detalle_trabajo_estado_idx ON comparacion.detalle (trabajo_id, estado);
CREATE INDEX detalle_comprobante_idx ON comparacion.detalle (tipo_cp, serie, numero);

-- Último estado conocido de cada comprobante, tomado de la comparación terminada más reciente.
CREATE VIEW comparacion.v_comprobante_ultimo_estado AS
SELECT DISTINCT ON (t.empresa_id, d.tipo_cp, d.serie, d.numero)
       t.empresa_id,
       d.tipo_cp,
       d.serie,
       d.numero,
       d.estado,
       t.periodo,
       t.id AS trabajo_id,
       t.finalizado_en
  FROM comparacion.detalle d
  JOIN nucleo.trabajo t ON t.id = d.trabajo_id
 WHERE t.estado = 'OK'
 ORDER BY t.empresa_id, d.tipo_cp, d.serie, d.numero, t.finalizado_en DESC;
