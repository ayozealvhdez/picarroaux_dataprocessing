# Python workflow for processing data from the backup Picarro analyser at Izaña Observatory

This analyser is a third instrument, operating independently of the Picarro systems used for GAW and ICOS. The processing workflow implemented here is simpler than those used for the other two Picarro instruments operated by the [Izaña Atmospheric Research Center](https://izana.aemet.es/). This instrument, internally known as the “Picarro aux” or “Picarro backup”, is used solely as a comparison instrument.

The workflow is designed for the ambient/target sampling sequence of the Picarro aux. It uses only two target tanks, each sampled for 30 minutes once per day; these measurements are used to derive a daily calibration curve.

Comparison with the more elaborate workflow used for the Picarro instrument operated for GAW at Izaña shows that the mean and median differences in CO2, CH4, and CO concentrations are on the order of 0.001–0.01 ppm for CO2 and 0.001–0.01 ppb for CH4 and CO. This is therefore a simple, useful, and functional solution that fully meets our needs.

The explanations, comments, and variable names are in Spanish because this script is primarily intended for internal use by the Izaña team.

## PASO 1. COPIA DE DATOS RAW

- Copia diaria de los datos raw desde la QNAP (`Z:\picarro-aux\DataLog_User`) hacia `tmp/raw_data`. Los días ya existentes en `tmp/raw_data` no se sobrescriben.
- Se copian los últimos 80 días completos hasta ayer (parámetro configurable al inicio de `main.py`). Son esos días los que se van a procesar (sin sobrescribir los que ya estén procesados), y los datos raw más antiguos se van borrando (ver paso 6 para más detalles).

## PASO 2. PREPROCESADO DE AMBIENTE Y TARGETS

- Lectura cronológica de los datos raw (archivos `.dat` en `tmp/raw_data`) de cada día.
- Para cada día, extracción de las columnas `CO2`, `CH4`, `CO`, `EPOCH_TIME`, `MPVPosition` y, si existe, `ALARM_STATUS`.
- División de los datos según `MPVPosition` y almacenamiento en ficheros separados para ambiente y targets dentro de `tmp/preprocessed_data`.
- Descarte de los primeros 10 min después de cada cambio a ambiente (parámetro configurable al inicio de `main.py`). También se convierten CH4 y CO de ppm a ppb.
- Generación de los flags `processing_flag_co2`, `processing_flag_ch4` y `processing_flag_co`: 1 si el valor es numérico y no hay alarma; 0 en caso contrario.

## PASO 3. PROCESADO DE TARGETS COMO INYECCIONES

- Cálculo de la media y la desviación estándar poblacional (`dof=0`) de cada gas dentro de cada inyección.
- Se considera una misma inyección cuando el salto entre medidas consecutivas con la misma `MPVPosition` no supera los 100 s (parámetro configurable al inicio de `main.py`).
- Descarte de los primeros 10 min de cada inyección (parámetro configurable al inicio de `main.py`). Solo se usan observaciones con `processing_flag_*=1` y se requieren al menos 100 por gas; si no, la media y la desviación quedan vacías.
- Agrupación de los resultados de CO2, CH4 y CO en una fila por inyección. El resultado se guarda en `processed_data/injections`.

## PASO 4. CÁLCULO DE CALIBRACIONES

- Lectura del histórico completo de inyecciones target ya procesadas (`processed_data/injections`).
- Emparejamiento de las inyecciones consecutivas con `MPVPosition=2` y `MPVPosition=3`.
- Si se repite una posición de target (`MPVPosition=2` o `MPVPosition=3`) antes de aparecer la otra, se conserva la inyección más reciente.
- Ajuste lineal para las tres especies, usando los valores de referencia de los targets (parámetros configurables al inicio de `main.py`) y la media de las inyecciones. Si falta alguna media para algún gas, se descarta la calibración de ese gas.
- En `processed_data/calibrations` se guardan ficheros con los parámetros de la calibración y otros parámetros útiles, como la fecha a partir de la cual la calibración es válida (= el final de la segunda inyección de target correspondiente).
- En `processed_data/calibration_curves` se guarda una gráfica PNG con los dos puntos de cada gas y el ajuste lineal.

## PASO 5. CALIBRACIÓN DEL AMBIENTE

- Lectura de todo el histórico de calibraciones lineales disponible.
- Selección, para cada medida y gas, de la calibración más reciente cuya fecha sea anterior o igual a la medida.
- Cálculo de las concentraciones corregidas mediante la transformación dada por el ajuste lineal. En este paso se registra la calibración utilizada para cada observación. Si el `processing_flag_*` es 0 o no existe una calibración anterior, la concentración corregida queda vacía.
- No se interpola entre la calibración anterior y la posterior ni se limita la antigüedad máxima de la calibración (es un procesado sencillo... y tenemos calibraciones diarias).
- Guardado de los datos procesados en `processed_data/ambient`, incluyendo el valor antes de corregir, el valor corregido y la fecha de la calibración empleada.

## PASO 6. LIMPIEZA DE DATOS TEMPORALES

- Si todas las etapas de procesado terminan correctamente, se eliminan los datos raw y preprocesados situados fuera del periodo configurado (por defecto: 80 días).
- Así se evita acumular demasiados ficheros temporales que llenen el disco duro. Solo se conservan indefinidamente los datos que hay en `processed_data` (promedios de inyecciones, datos de ambiente procesados, calibraciones).

NOTA: Los resultados ya existentes no se recalculan ni se sobrescriben. Si quiere que se recalculen los datos procesados de un día, primero hay que borrar el subdirectorio correspondiente y luego correr el código.
