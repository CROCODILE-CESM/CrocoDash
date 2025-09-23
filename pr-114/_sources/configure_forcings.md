# Setting up your forcings

To set up the forcings for your previously not included raw data product, a product information, path to the raw data, and product name must be provided

These can be passed into the configure forcings arguments to set up a set of code to take the product information and setup initial and boundary conditions. For cesm output, simply add the path, the product information (As a dict like in raw_data_access/config), and the product name "CESM_OUTPUT". This will copy a folder of code into your input directory that is then run during process forcings. Why this is useful is you can then edit the processing code as issues come up, inlcuding unit conversions issues among other problems. You can edit the code in your input directory and run it using the driver script. 
