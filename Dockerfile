FROM continuumio/miniconda3:25.3.1-1

# System packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    git make curl build-essential && \
    rm -rf /var/lib/apt/lists/*

ENV WORKDIR=/workspace
ENV CESMROOT=/workspace/CESM
ENV CIME_MACHINE=ubuntu-latest
ENV DIN_LOC_ROOT=/workspace
ENV CIME_OUTPUT_ROOT=/workspace
ENV USER=crocobot
WORKDIR ${WORKDIR}

# ---- Install CESM ----
RUN git clone https://github.com/CROCODILE-CESM/CESM.git ${CESMROOT} -b workshop_2025 && \
    cd ${CESMROOT} && ./bin/git-fleximod update

# ---- Copy CrocoDash only for environment build ----
COPY CrocoDash/ ${WORKDIR}/CrocoDash/
WORKDIR ${WORKDIR}/CrocoDash

# ---- Compute environment hash ----
# This will go inside the container for CI comparison
RUN sha256sum ${WORKDIR}/CrocoDash/environment.yml > /env_hash.txt

# ---- Create conda environment ----
RUN conda env create -f ${WORKDIR}/CrocoDash/environment.yml -y


# ---- Default shell & entry ----
SHELL ["/bin/bash", "-c"]
ENV PATH=/opt/conda/envs/CrocoDash/bin:$PATH
