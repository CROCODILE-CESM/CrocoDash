from pathlib import Path
from CrocoDash.extract_obc.parse_dataset import parse_dataset

def test_parse_dataset(skip_if_not_glade):

    sample_ds_path = Path("/glade/campaign/collections/cmip/CMIP6/CESM-HR/FOSI_BGC/HR/g.e22.TL319_t13.G1850ECOIAF_JRA_HR.4p2z.001/ocn/proc/tseries/month_1")
    vars = ["DIC","DOC"]
    variable_info = parse_dataset(vars, sample_ds_path)
    assert "/glade/campaign/collections/cmip/CMIP6/CESM-HR/FOSI_BGC/HR/g.e22.TL319_t13.G1850ECOIAF_JRA_HR.4p2z.001/ocn/proc/tseries/month_1/g.e22.TL319_t13.G1850ECOIAF_JRA_HR.4p2z.001.pop.h.J_DIC_ALT_CO2.201301-201312.nc" in variable_info["DIC"]
    assert "/glade/campaign/collections/cmip/CMIP6/CESM-HR/FOSI_BGC/HR/g.e22.TL319_t13.G1850ECOIAF_JRA_HR.4p2z.001/ocn/proc/tseries/month_1/g.e22.TL319_t13.G1850ECOIAF_JRA_HR.4p2z.001.pop.h.DOCr_remin_zint.197701-197712.nc" in variable_info["DOC"]
