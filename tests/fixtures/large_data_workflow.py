import pytest
import pandas as pd


@pytest.fixture
def generate_piecewise_raw_data(tmp_path):
    def _factory(ds, start_date, end_date, filename_starter=""):

        # Convert date strings to pandas datetime objects
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)

        # Create output directory
        output_dir = tmp_path / "piecewise"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Loop through the date range in 5-day increments
        current_date = start
        while current_date <= end:
            next_date = min(current_date + pd.Timedelta(days=5), end)

            # Generate output filename
            filename = (
                filename_starter
                + f"{current_date.strftime('%Y%m%d')}_{next_date.strftime('%Y%m%d')}.nc"
            )
            ds.to_netcdf(output_dir / filename)

            current_date = next_date + pd.Timedelta(days=1)

        return output_dir

    return _factory
