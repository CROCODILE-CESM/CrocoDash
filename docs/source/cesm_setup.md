(cesm)=

# CESM Setup

The first step in running an ocean model inside the CESM is setting up the CESM! Here's how to do it:

## Step 1: Clone the repo

CROCODILE has its own fork of the CESM available here: <https://github.com/CROCODILE-CESM/CESM>. Go ahead and clone it as shown below. I'm gonna call mine CROCESM.

```bash
git clone https://github.com/CROCODILE-CESM/CESM CROCESM -b workshop_2025
```

## Step 2: Checkout all the components

The original clone only clones the CESM code, we need to checkout all of the components as well, like the ocean model and the sea ice model. This will take some time.

```bash
cd CROCESM
./bin/git-fleximod update
```

## Step 3: Done!

We're done! Remember this path, and install CrocoDash!
