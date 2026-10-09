# Tested configurations

Each week, cases built by CrocoDash `main` run MOM_interface's regional smoke tests on Derecho, against the `crocodash` branch of [CROCODILE-CESM/CESM](https://github.com/CROCODILE-CESM/CESM) (see [crocontainer's `cesm_tests`](https://github.com/CROCODILE-CESM/crocontainer/tree/main/cesm_tests)):

| Compset | Components | SMS_D_Ld2 |
|---|---|---|
| `CR_JRA_GLOFAS` | MOM6 + GLOFAS runoff | ![](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CROCODILE-CESM/crocontainer/test-results/SMS_D_Ld2.CR_JRA_GLOFAS.json) |
| `CR1850MARBL_JRA_GLOFAS` | + MARBL | ![](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CROCODILE-CESM/crocontainer/test-results/SMS_D_Ld2.CR1850MARBL_JRA_GLOFAS.json) |
| `GR_JRA_GLOFAS` | + CICE | ![](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CROCODILE-CESM/crocontainer/test-results/SMS_D_Ld2.GR_JRA_GLOFAS.json) |
| `CWR_JRA_GLOFAS` | + WW3 | ![](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CROCODILE-CESM/crocontainer/test-results/SMS_D_Ld2.CWR_JRA_GLOFAS.json) |
| `GWR1850MARBL_JRA_GLOFAS` | MOM6 + CICE + WW3 + MARBL + GLOFAS | ![](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CROCODILE-CESM/crocontainer/test-results/SMS_D_Ld2.GWR1850MARBL_JRA_GLOFAS.json) |
