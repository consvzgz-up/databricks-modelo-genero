# Cómo consultar el endpoint `genero-cliente`

Modelo que predice el género musical probable de un cliente a partir de su proveedor de correo, país y ciudad.
Entrenado cada día por un job de Databricks y publicado en un endpoint de Databricks Model Serving.

## Datos de acceso

| Dato | Valor |
|---|---|
| URL del endpoint | `https://dbc-c19856c3-faa2.cloud.databricks.com/serving-endpoints/genero-cliente/invocations` |
| Token de acceso | se entrega por separado; va en la cabecera `Authorization: Bearer <token>` |
| Método | `POST`, cuerpo JSON, cabecera `Content-Type: application/json` |

## Entrada

Una lista de registros con tres campos de texto:

| Campo | Qué es | Ejemplo |
|---|---|---|
| `tipo_correo` | proveedor del correo (`gmail`, `yahoo`, `hotmail`...); también se acepta el correo completo | `yahoo` o `ana@yahoo.com.br` |
| `pais` | país del cliente | `Germany` |
| `ciudad` | ciudad del cliente | `Berlin` |

## Ejemplo con curl

Sustituya `PEGUE_AQUI_EL_TOKEN` por el token, sin comillas ni signos `<` `>`:

```bash
curl -X POST https://dbc-c19856c3-faa2.cloud.databricks.com/serving-endpoints/genero-cliente/invocations \
  -H "Authorization: Bearer PEGUE_AQUI_EL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dataframe_records": [{"tipo_correo": "yahoo", "pais": "Germany", "ciudad": "Berlin"}]}'
```

En Git Bash o PowerShell de Windows, el cuerpo va con comillas dobles escapadas:

```bash
curl -X POST https://dbc-c19856c3-faa2.cloud.databricks.com/serving-endpoints/genero-cliente/invocations -H "Authorization: Bearer PEGUE_AQUI_EL_TOKEN" -H "Content-Type: application/json" -d "{\"dataframe_records\": [{\"tipo_correo\": \"yahoo\", \"pais\": \"Germany\", \"ciudad\": \"Berlin\"}]}"
```

## Ejemplo con Python

```python
import os, requests

URL = "https://dbc-c19856c3-faa2.cloud.databricks.com/serving-endpoints/genero-cliente/invocations"
TOKEN = os.environ["DATABRICKS_TOKEN"]          # el token, guardado en una variable de entorno

respuesta = requests.post(
    URL,
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    json={"dataframe_records": [
        {"tipo_correo": "yahoo", "pais": "Germany", "ciudad": "Berlin"},
        {"tipo_correo": "gmail", "pais": "Brazil", "ciudad": "São Paulo"},
    ]},
    timeout=60,
)
print(respuesta.status_code)
print(respuesta.json())
```

## Respuesta

Un objeto `predictions` con un resultado por registro enviado, en el mismo orden:

```json
{
  "predictions": [
    {
      "genero": "Metal",
      "top_1": "Metal", "p_1": 0.4076,
      "top_2": "Rock", "p_2": 0.3364,
      "top_3": "Alternative & Punk", "p_3": 0.0752
    }
  ]
}
```

`genero` es el género predicho; `top_1` a `top_3` son los tres géneros más probables con su probabilidad.

## Si algo falla

| Respuesta | Causa | Solución |
|---|---|---|
| `401 Credential was not sent or was of an unsupported type` | el token no llegó bien (falta, con `<` `>`, o con espacios) | revise la cabecera `Authorization: Bearer <token>` |
| `403` | el token no tiene permiso sobre este endpoint o ya venció | pida un token nuevo |
| la primera llamada tarda más de lo normal | el endpoint se apaga cuando no se usa y arranca con la primera petición | espere y reintente; las siguientes responden en segundos |
| `400` con mención a columnas | falta alguno de los tres campos o el nombre está mal escrito | use exactamente `tipo_correo`, `pais`, `ciudad` |

Código y documentación completa: https://github.com/consvzgz-up/databricks-modelo-genero
