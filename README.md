# Crocodile Regional Ruckus

## Background
 The independent, strong, package that sets up a regional MOM run is the regional-mom6 (RM6) package. There's a few things we wanted to add that are specific to the CESM, because we are running MOM inside the CESM. There's also new ways we want to gather grids that uses files on the NCAR glade file system.

## Motivation: 
There's a few different motivations. Since we have some, almost, "NCAR-specific" things, we don't want to put those into the *independent* package, RM6. In the spirit of that, Ashley developed an additional module/package called regional-casegen to setup the CESM side of things that takes in input from the RM6 workflow. Then, we needed to incorporate the new way of gathering grids. That's another module. This forces or speaks for the idea of a framework to use all the modules in this workflow. Having an overall umbrella that can work with multiple packages without fiddling with RM6 is an attractive proposition.

## Description: 
The framework here is called Crocodile Regional Ruckus (CRR). It, currently, holds four modules grid_gen, boundary_conditions, RM6, and regional-casegen. It's a lightweight package that ties together each part of the process into one package. A large part of the code is wrapping RM6. The major difference between RM6 and CRR is that CRR brings in the NCAR and derecho specific dependencies. CRR also uses explicit function definitions, so every function is completely standalone. This is a style change from regional mom6, which relies heavily on variables defined in the class object. Based on what style the user prefers, they can use RM6 to work through a workflow of setting up a regional case with CRR function calls at either end for grid generation and cesm setup, OR they can use just CRR to explicity call a function or two they require all the way up to the entire workflow. See a visualization: https://drive.google.com/file/d/1Y1FQnT741pcLVVOOl5qS1JphsuiXnVLv/view?usp=sharing

## Getting Familiar (Installation): 
Going with this flow, there are two demos to get used to the CRR. One is a "minimal_demo" that uses CRR for grid generation and regional casegen, but still majority uses RM6. It copies almost directly from the RM6 demo to show how little of a change it can be. The other demo is a "with_CRR" demo that uses CRR for everything. That still means a majority use of RM6, but just under the hood.

Since CRR is derecho specific, we can add it to the python module search path from my dir and just use it. It's shown in the demo. OR you can clone it with git clone --recurse-submodules [link]. For the environment, on derecho, this path can work: /glade/work/manishrv/conda-envs/vroom_clean_env