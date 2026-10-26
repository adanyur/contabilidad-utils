-- Núcleo compartido por todos los procesos: empresas, archivos cargados y trabajos.

CREATE SCHEMA IF NOT EXISTS nucleo;

CREATE TABLE nucleo.empresa (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ruc           char(11)     NOT NULL UNIQUE CHECK (ruc ~ '^[0-9]{11}$'),
    razon_social  varchar(200) NOT NULL,
    activo        boolean      NOT NULL DEFAULT true,
    creado_en     timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE nucleo.proceso (
    codigo  varchar(30)  PRIMARY KEY,
    nombre  varchar(100) NOT NULL,
    cola    varchar(50)  NOT NULL,  -- nombre de la cola pgmq
    activo  boolean      NOT NULL DEFAULT true
);

INSERT INTO nucleo.proceso (codigo, nombre, cola)
VALUES ('COMPARACION', 'Comparación SIRE vs Bizlinks', 'comparacion');

CREATE TABLE nucleo.carga_archivo (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empresa_id      bigint       NOT NULL REFERENCES nucleo.empresa (id),
    periodo         char(6)      NOT NULL CHECK (periodo ~ '^[0-9]{4}(0[1-9]|1[0-2])$'),
    tipo_origen     varchar(20)  NOT NULL CHECK (tipo_origen IN ('SIRE_RVIE')),
    nombre_archivo  varchar(255) NOT NULL,
    contenido       bytea        NOT NULL,
    hash_archivo    char(64)     NOT NULL,  -- sha256 en hexadecimal
    tamano_bytes    integer      NOT NULL,
    usuario         varchar(100),
    cargado_en      timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX carga_archivo_hash_idx ON nucleo.carga_archivo (empresa_id, periodo, hash_archivo);

-- Estado visible e historial de ejecuciones. La cola en sí es pgmq; aquí se guarda lo que ve el usuario.
CREATE TABLE nucleo.trabajo (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proceso_codigo    varchar(30)  NOT NULL REFERENCES nucleo.proceso (codigo),
    empresa_id        bigint       NOT NULL REFERENCES nucleo.empresa (id),
    periodo           char(6)      NOT NULL,
    carga_archivo_id  bigint       REFERENCES nucleo.carga_archivo (id),
    parametros        jsonb        NOT NULL DEFAULT '{}',
    estado            varchar(15)  NOT NULL DEFAULT 'PENDIENTE'
                      CHECK (estado IN ('PENDIENTE', 'EN_PROCESO', 'OK', 'ERROR', 'CANCELADO')),
    progreso          smallint     NOT NULL DEFAULT 0 CHECK (progreso BETWEEN 0 AND 100),
    mensaje           text,
    intentos          smallint     NOT NULL DEFAULT 0,
    max_intentos      smallint     NOT NULL DEFAULT 3,
    msg_id            bigint,      -- id del mensaje en pgmq
    worker_id         varchar(100),
    usuario           varchar(100),
    creado_en         timestamptz  NOT NULL DEFAULT now(),
    iniciado_en       timestamptz,
    heartbeat_en      timestamptz,
    finalizado_en     timestamptz
);

CREATE INDEX trabajo_empresa_periodo_idx ON nucleo.trabajo (empresa_id, periodo, creado_en DESC);
CREATE INDEX trabajo_creado_idx ON nucleo.trabajo (creado_en DESC);
