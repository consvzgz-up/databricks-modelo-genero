-- Vista para el modelo predictivo: 4 campos
--   tipo_correo : proveedor del correo (texto entre '@' y el primer '.'): gmail, yahoo, hotmail, embraer...
--   pais        : país del cliente
--   ciudad      : ciudad del cliente
--   genero      : género musical de cada track comprado por el cliente
-- Una fila por track comprado: customer -> invoice -> invoice_line -> track -> genre
-- Misma vista que pipeline-db-ml/db/view.sql, con nombres de tres niveles de Unity Catalog.

CREATE OR REPLACE VIEW workspace.chinook.vw_cliente_genero AS
SELECT
    lower(split_part(split_part(c.email, '@', 2), '.', 1)) AS tipo_correo,
    c.country AS pais,
    c.city    AS ciudad,
    g.name    AS genero
FROM workspace.chinook.customer     c
JOIN workspace.chinook.invoice      i  ON i.customer_id = c.customer_id
JOIN workspace.chinook.invoice_line il ON il.invoice_id = i.invoice_id
JOIN workspace.chinook.track        t  ON t.track_id    = il.track_id
JOIN workspace.chinook.genre        g  ON g.genre_id    = t.genre_id;
