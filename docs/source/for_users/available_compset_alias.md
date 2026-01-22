# Available Compset Aliases

Regional compsets are available by checking out the CROCODILE-CESM/CESM fork. You can always use the long names of the compsets instead.

The only job of the %REGIONAL flag on MOM6 in the compset longnames below is that it sets an xml variable MOM6_DOMAIN_TYPE=REGIONAL, which shifts input parameters to regional defaults.

| Alias | Long name | Description |
|---|---|---|
| CR_JRA | 1850_DATM%JRA_SLND_SICE_MOM6%REGIONAL_SROF_SGLC_SWAV | Standalone ocean with data atmosphere from JRA |
| CR1850MARBL_JRA | 1850_DATM%JRA_SLND_SICE_MOM6%REGIONAL%MARBL-BIO_SROF_SGLC_SWAV | ocean coupled with MARBL BGC model with data atmosphere from JRA |
| CR_JRA_GLOFAS | 1850_DATM%JRA_SLND_SICE_MOM6%REGIONAL_DROF%GLOFAS_SGLC_SWAV | Standalone ocean with data atmosphere from JRA and data runoff from GLOFAS |
| CR1850MARBL_JRA_GLOFAS | 1850_DATM%JRA_SLND_SICE_MOM6%REGIONAL%MARBL-BIO_DROF%GLOFAS_SGLC_SWAV | ocean coupled with MARBL BGC model with data atmosphere from JRA and data runoff from GLOFAS|
| GR_JRA | 1850_DATM%JRA_SLND_CICE_MOM6%REGIONAL_SROF_SGLC_SWAV | ocean coupled with CICE sea ice model with data atmosphere from JRA |
| GR1850MARBL_JRA | 1850_DATM%JRA_SLND_CICE_MOM6%REGIONAL%MARBL-BIO_SROF_SGLC_SWAV | ocean coupled with MARBL BGC model and CICE sea ice model with data atmosphere from JRA |
| GR_JRA_GLOFAS | 1850_DATM%JRA_SLND_CICE_MOM6%REGIONAL_DROF%GLOFAS_SGLC_SWAV | ocean coupled with CICE sea ice model with data atmosphere from JRA and data runoff from GLOFAS |
| GR1850MARBL_JRA_GLOFAS | 1850_DATM%JRA_SLND_CICE_MOM6%REGIONAL%MARBL-BIO_DROF%GLOFAS_SGLC_SWAV | ocean coupled with MARBL BGC model and CICE sea ice model with data atmosphere from JRA and data runoff from GLOFAS|

