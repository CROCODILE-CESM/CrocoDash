# CESM not ported?

Is the CESM not ported onto your HPC or local machine? 

No worries! You can still use CrocoDash to construct all of your input files and print out all of your input parameters. Simply:

1. Follow all installation steps, including cloning the CESM.
2. When you create your case with the Case(....) step, use the argument machine = "CESM_NOT_PORTED" (still pass in the path to the CESM, we still use that!). This will not create your case and instead will print out and generate all required input files.