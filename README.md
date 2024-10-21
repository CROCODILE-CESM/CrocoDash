# Crocodile Regional Ruckus

## Background
 The independent, strong, package that sets up a regional MOM run is the regional-mom6 (RM6) package. There's a few things we wanted to add that are specific to the CESM, because we are running MOM inside the CESM. There's also new ways we want to gather grids that uses files on the NCAR glade file system.

## Motivation: 
There's a few different motivations. Since we have some, almost, "NCAR-specific" things, we don't want to put those into the *independent* package, RM6. In the spirit of that, Ashley developed an additional module/package called regional-casegen to setup the CESM side of things that takes in input from the RM6 workflow. Then, we needed to incorporate the new way of gathering grids. This resulted in the idea of a framework to use all the modules in this workflow. Having an overall umbrella that can work with multiple packages without fiddling with RM6 is an attractive proposition.

## Description: 
The framework here is called Crocodile Regional Ruckus (CRR). The major difference between RM6 and CRR is that CRR brings in the NCAR and derecho specific dependencies. It, currently, holds four modules grid_gen, boundary_conditions (not developed), RM6, and regional-casegen. 

It's a lightweight package that ties together each part of the NCAR/Derecho process into one package. There's two avenues of development:

1. (Decided to table for now) One avenue is the idea of wrapping RM6. A large part of the code is wrapping RM6. Two reasons to do that, CRR uses explicit function definitions, so every function is completely standalone. This is a style change from regional mom6, which relies heavily on variables defined in the class object. The other part of that is users can use just CRR to explicity call a function or two they require. See a visualization: https://drive.google.com/file/d/1Y1FQnT741pcLVVOOl5qS1JphsuiXnVLv/view?usp=sharing

2. (Current development) The second avenue is instead of having CRR wrap RM6, have it be *adjacent* to RM6. Users would call CRR grid_gen and regional_casegen functions as well as RM6 functions directly. This requires the least additional code and keeps up development in a sane space. 



## Getting Familiar (Installation): 

Installation:
1. The first step is cloning *WITH* the submodules:
`git clone --recurse-submodules git@github.com:CROCODILE-CESM/crocodile-regional-ruckus.git`
2. Install the environment (which we fail if the submodules aren't installed):
`mamba env create -f environment.yml`
3. Activate the environment:
`mamba activate crr`

Going with this flow, there are two demos (one for each avenue) to get used to the CRR. 

1. One is a "minimal_demo" that uses CRR for grid generation and regional casegen, but still majority uses RM6 experiment. It copies almost directly from the RM6 demo to show how little of a change it can be. This is the one that is most strongly supported.

2. The other demo is the other extreme and is a "with_CRR" demo that uses CRR for everything. That still means a majority use of RM6, but just under the hood. The idea with this demo is to show that any of the functions in RM6 can be swapped out incase that's all we need. 

## Documentation: 

Check out our documentation in the docs/ folder. When it is published, we'll add a link here!

