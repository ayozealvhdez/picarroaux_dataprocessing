# Python workflow for processing data from the backup Picarro analyser at Izaña Observatory

This workflow supports the backup Picarro G2401 analyser at the [Izaña Atmospheric Research Center](https://izana.aemet.es/), internally known as the “Picarro aux” or “Picarro backup”. The analyser is a third instrument, operating independently of the Picarro G2401 systems used for GAW and ICOS, and is employed solely as a comparison instrument. Its processing workflow is therefore simpler than those used for the other two analysers.

The workflow is designed for the ambient/target sampling sequence of the Picarro aux. It uses only two target tanks, each sampled for 30 minutes once per day, and their measurements are used to derive a daily calibration curve. Although they therefore function as calibration tanks, we refer to them as targets because they are sampled according to a schedule very similar to that used for target tanks on other instruments at Izaña.

Comparison with the more elaborate workflow used for the Picarro instrument operated for GAW at Izaña shows that the mean and median differences in CO2, CH4, and CO concentrations are on the order of 0.001–0.01 ppm for CO2 and 0.001–0.01 ppb for CH4 and CO. This is therefore a simple, useful, and functional solution that fully meets our needs.

The code is public to support the scientific community, since it may be useful as a reference or starting point for similar Picarro data-processing applications.

The comments, variable names, and file names are in Spanish because this script was primarily conceived for internal use by the Izaña team.

## Requirements

- Python 3.11–3.14 (Python 3.14 recommended)
- Dependencies listed in [`requirements.txt`](requirements.txt)

## License

This project is released under an [Academic Non-Commercial License](LICENSE). The repository may be used, copied, and modified for non-commercial academic research, teaching, and scientific work. Commercial use requires prior written permission from the copyright holder. Input observational data are not distributed under this license.

> **Note:** This workflow includes installation-specific configuration, such as data paths, instrument settings, target reference values, and processing parameters. Adapt these settings to your local setup before use.

## Processing workflow

The workflow runs incrementally and is organized into the following stages. Existing results are neither recalculated nor overwritten.

### Step 1. Raw data copy

- Daily copy of the raw data from the raw data storage system (`Z:\picarro-aux\DataLog_User`) to `tmp/raw_data`. Days already present in `tmp/raw_data` are not overwritten.
- The latest 80 complete days up to yesterday are copied (parameter configurable at the beginning of `main.py`). These are the days that will be processed (without overwriting those already processed), while older raw data are progressively deleted (see Step 6 for more details). Because existing days are not overwritten, a daily scheduled run will normally copy only the previous day's raw data. If the workflow has not run for several days, it will also copy any missing days within the configured processing period.

### Step 2. Preprocessing of ambient and target data

- Chronological reading of the raw data (the `.dat` files in `tmp/raw_data`) for each day.
- For each day, extraction of the `CO2`, `CH4`, `CO`, `EPOCH_TIME`, `MPVPosition` and, if present, `ALARM_STATUS` columns.
- Data are split according to `MPVPosition` and stored in separate files for ambient and target data within `tmp/preprocessed_data`.
- The first 10 min after each switch to ambient air are discarded (parameter configurable at the beginning of `main.py`). CH4 and CO are also converted from ppm to ppb.
- Generation of the `processing_flag_co2`, `processing_flag_ch4`, and `processing_flag_co` flags: 1 if the value is numeric and there is no alarm; 0 otherwise.

### Step 3. Processing targets as injections

- Calculation of the mean and population standard deviation (`dof=0`) of each gas within each injection.
- Measurements are considered part of the same injection when the gap between consecutive measurements with the same `MPVPosition` does not exceed 100 s (parameter configurable at the beginning of `main.py`).
- The first 10 min of each injection are discarded (parameter configurable at the beginning of `main.py`). Only observations with `processing_flag_*=1` are used, and at least 100 observations per gas are required; otherwise, the mean and standard deviation are left empty.
- The CO2, CH4, and CO results are grouped into one row per injection. The result is saved in `processed_data/injections`.

### Step 4. Calibration calculation

- Reading of the complete history of already processed target injections (`processed_data/injections`).
- Pairing of consecutive injections with `MPVPosition=2` and `MPVPosition=3`.
- If a target position (`MPVPosition=2` or `MPVPosition=3`) is repeated before the other one appears, the most recent injection is retained.
- Linear fitting for the three species, using the target reference values (parameters configurable at the beginning of `main.py`) and the injection means. If any mean is missing for a given gas, the calibration for that gas is discarded.
- Files containing the calibration parameters and other useful parameters are saved in `processed_data/calibrations`, including the date from which the calibration is valid (i.e., the end of the corresponding second target injection).
- A PNG plot with the two points for each gas and the linear fit is saved in `processed_data/calibration_curves`.

### Step 5. Ambient calibration

- Reading of the full available history of linear calibrations.
- For each measurement and gas, selection of the most recent calibration whose date is earlier than or equal to the measurement date.
- Calculation of the corrected concentrations using the transformation given by the linear fit. The calibration used for each observation is recorded at this stage. If `processing_flag_*` is 0 or no earlier calibration exists, the corrected concentration is left empty.
- No temporal interpolation is performed between the previous and subsequent calibrations, and no maximum calibration age is imposed (this is a simple processing workflow... and we have daily calibrations).
- The processed data are saved in `processed_data/ambient`, including the value before correction, the corrected value, and the date of the calibration used.

### Step 6. Temporary data cleanup

- If all processing stages finish successfully, raw and preprocessed data outside the configured period (80 days by default) are deleted. This prevents the accumulation of too many temporary files that could fill the hard drive. Only the data in `processed_data` are retained indefinitely (injection averages, processed ambient data, and calibrations).

> **Note:** To recalculate the processed data for a given day, first delete the corresponding subdirectory and run the code again.
