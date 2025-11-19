from CrocoDash.raw_data_access.base import *

class TPXO(BaseProduct):
    product_name = "tpxo"
    description = "TPXO (TOPEX/POSEIDON Global Tidal Ocean I think) is a public tidal model dataset"
    link = "https://www.tpxo.net/global"


class CESMInputData(BaseProduct):
    product_name = "CESM Inputdata"
    description = "The CESM Input SVN repo holds all files CrocoDash exposes publicly themselves at the following repo link"
    link = "https://svn-ccsm-inputdata.cgd.ucar.edu/trunk/inputdata/ocn/mom/croc"
    