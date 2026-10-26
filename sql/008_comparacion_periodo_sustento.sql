-- Cabecera por empresa + periodo, sustento de comprobantes y cierre.
--
-- Cada nueva carga del SIRE de un periodo borra el detalle de las cargas anteriores y deja el suyo:
-- la cabecera apunta a la carga vigente. El sustento se guarda por CAR, fuera del detalle, para que
-- sobreviva a las recargas. El periodo se cierra cuando todo lo que requiere sustento está SUSTENTADO;
-- cerrado no admite cargas hasta que se reabre.

CREATE TABLE comparacion.periodo (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empresa_id          bigint      NOT NULL REFERENCES nucleo.empresa (id),
    periodo             char(6)     NOT NULL CHECK (periodo ~ '^[0-9]{4}(0[1-9]|1[0-2])$'),
    estado              varchar(10) NOT NULL DEFAULT 'ABIERTO' CHECK (estado IN ('ABIERTO', 'CERRADO')),
    trabajo_vigente_id  bigint      REFERENCES nucleo.trabajo (id),  -- carga cuyo detalle está en comparacion.detalle
    creado_en           timestamptz NOT NULL DEFAULT now(),
    actualizado_en      timestamptz NOT NULL DEFAULT now(),
    cerrado_en          timestamptz,
    cerrado_por         varchar(100),
    UNIQUE (empresa_id, periodo)
);

-- Bitácora del periodo: cargas, cierres y reaperturas
CREATE TABLE comparacion.periodo_evento (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    periodo_id  bigint      NOT NULL REFERENCES comparacion.periodo (id) ON DELETE CASCADE,
    tipo        varchar(15) NOT NULL CHECK (tipo IN ('CARGA', 'CIERRE', 'REAPERTURA')),
    trabajo_id  bigint      REFERENCES nucleo.trabajo (id),
    comentario  text,
    usuario     varchar(100),
    creado_en   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX periodo_evento_periodo_idx ON comparacion.periodo_evento (periodo_id, creado_en DESC);

CREATE TABLE comparacion.motivo_sustento (
    codigo       varchar(30)  PRIMARY KEY,
    descripcion  varchar(200) NOT NULL,
    activo       boolean      NOT NULL DEFAULT true,
    orden        smallint     NOT NULL DEFAULT 0
);

INSERT INTO comparacion.motivo_sustento (codigo, descripcion, orden) VALUES
    ('RECHAZADO_SUNAT',   'Rechazado por SUNAT: no corresponde al registro de ventas', 10),
    ('PERIODO_SIGUIENTE', 'Se registrará en el periodo siguiente (emitido o informado tarde)', 20),
    ('ANULACION',         'Anulación o comunicación de baja posterior', 30),
    ('ERROR_SIRE',        'Error en el registro del SIRE', 40),
    ('ERROR_BIZLINKS',    'Error en Bizlinks / OSE', 50),
    ('REDONDEO',          'Diferencia de redondeo', 60),
    ('OPERACION_ESPECIAL', 'Operación exonerada, inafecta, gratuita o con anticipo', 70),
    ('OTRO',              'Otro (detallar en el comentario)', 99);

-- Sustento vigente de cada comprobante del periodo, por CAR
CREATE TABLE comparacion.sustento (
    periodo_id      bigint      NOT NULL REFERENCES comparacion.periodo (id) ON DELETE CASCADE,
    car             varchar(27) NOT NULL,
    estado          varchar(15) NOT NULL CHECK (estado IN ('PENDIENTE', 'SUSTENTADO', 'EN_CORRECCION')),
    motivo          varchar(30) REFERENCES comparacion.motivo_sustento (codigo),
    comentario      text,
    usuario         varchar(100),
    actualizado_en  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (periodo_id, car)
);

CREATE TABLE comparacion.sustento_historial (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    periodo_id  bigint      NOT NULL,
    car         varchar(27) NOT NULL,
    estado      varchar(15) NOT NULL,
    motivo      varchar(30),
    comentario  text,
    usuario     varchar(100),
    trabajo_id  bigint,     -- carga vigente cuando se registró
    creado_en   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX sustento_historial_idx ON comparacion.sustento_historial (periodo_id, car, creado_en DESC);

-- Qué comprobantes del detalle necesitan sustento para cerrar el periodo: con diferencia, solo SIRE,
-- solo Bizlinks (salvo rechazados por SUNAT, que se sustentan solos) e IGV observado.
ALTER TABLE comparacion.detalle ADD COLUMN IF NOT EXISTS requiere_sustento boolean NOT NULL DEFAULT false;

UPDATE comparacion.detalle
   SET requiere_sustento = estado IN ('DIFERENCIA', 'SOLO_SIRE')
                        OR (estado = 'SOLO_BIZLINKS' AND coalesce(biz_estado, '') NOT LIKE '%RC_05')
                        OR igv_observado;

CREATE INDEX IF NOT EXISTS detalle_requiere_sustento_idx ON comparacion.detalle (trabajo_id) WHERE requiere_sustento;

-- Cabeceras de lo que ya existe: una por empresa + periodo, con la última carga terminada como vigente.
-- El detalle de las cargas anteriores se conserva; se reemplaza con la próxima carga del periodo.
INSERT INTO comparacion.periodo (empresa_id, periodo, trabajo_vigente_id)
SELECT t.empresa_id, t.periodo,
       (SELECT max(v.id) FROM nucleo.trabajo v
         WHERE v.empresa_id = t.empresa_id AND v.periodo = t.periodo AND v.estado = 'OK'
           AND v.proceso_codigo = 'COMPARACION')
  FROM nucleo.trabajo t
 WHERE t.proceso_codigo = 'COMPARACION'
 GROUP BY t.empresa_id, t.periodo;

INSERT INTO comparacion.periodo_evento (periodo_id, tipo, trabajo_id, comentario, usuario, creado_en)
SELECT p.id, 'CARGA', t.id, 'Carga anterior a la cabecera de periodo', t.usuario, t.finalizado_en
  FROM comparacion.periodo p
  JOIN nucleo.trabajo t ON t.empresa_id = p.empresa_id AND t.periodo = p.periodo
 WHERE t.estado = 'OK' AND t.proceso_codigo = 'COMPARACION';
