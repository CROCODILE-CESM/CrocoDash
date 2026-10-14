import queryearth as qe


def registry() -> qe.Registry:
    """Build the CrocoDash registry."""

    dimensions = [
        qe.Axis("resolution", "km"),
        qe.Labels("product"),
        qe.Labels("variable"),
    ]
    registry = qe.Registry(dimensions=dimensions)  # Space and Time are default added
    registry.add(
        qe.Rule(
            code="CROC001",
            title="Turn off GM parametrization at high resolution",
            message="Below 8 km, eddies are partly resolved, so GM thickness diffusion is usually turned off.",
            changes=[qe.Change("MOM_input", "THICKNESSDIFFUSE", False)],
            scope=qe.Scope(dimensions={"resolution": {"lt": 8}}),
        )
    )

    CAPS_60 = {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [[-180, 60], [180, 60], [180, 90], [-180, 90], [-180, 60]]
            ],  # north of 60°N
            [
                [[-180, -90], [180, -90], [180, -60], [-180, -60], [-180, -90]]
            ],  # south of 60°S
        ],
    }

    registry.add(
        qe.Rule(
            code="CROC010",
            level="warning",
            title="Consider active sea ice (CICE)",
            message="Part of this domain is poleward of 60 degrees, where sea ice forms in winter.",
            changes=[qe.Change("compset", "ice", "CICE")],
            scope=qe.Scope(space=qe.space.polygon(CAPS_60)),
        )
    )
    return registry


if __name__ == "__main__":
    reg = registry()
    print(reg)
