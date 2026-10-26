-- El cruce SIRE vs Bizlinks es por CAR SUNAT (Código de Anotación de Registro):
-- RUC (11) + tipo (2) + serie (4) + número con ceros (10). Bizlinks no lo guarda; se arma con sus datos.

ALTER TABLE comparacion.detalle ADD COLUMN IF NOT EXISTS car varchar(27);

-- Comparaciones anteriores: se arma con el RUC de la empresa del trabajo
UPDATE comparacion.detalle d
   SET car = e.ruc || d.tipo_cp || d.serie || lpad(d.numero::text, 10, '0')
  FROM nucleo.trabajo t
  JOIN nucleo.empresa e ON e.id = t.empresa_id
 WHERE t.id = d.trabajo_id AND d.car IS NULL;

CREATE INDEX IF NOT EXISTS detalle_car_idx ON comparacion.detalle (car);
