def convert_lons_to_180_range(**lons):
    lons_adj = []
    for lon in lons:
        lons_adj.append((lon+180) %360 - 180)
    return lons