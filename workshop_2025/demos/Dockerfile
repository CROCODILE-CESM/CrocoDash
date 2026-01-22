FROM continuumio/miniconda3:25.3.1-1



# ---- System dependencies ----
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        make \
        curl \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

# ---- Set working directory and CESMROOT ----
ENV WORKDIR=/workspace \
    CESMROOT=/workspace/CESM
WORKDIR ${WORKDIR}

# ---- Clone CESM and run git-fleximod ----
RUN git clone https://github.com/CROCODILE-CESM/CESM.git ${CESMROOT} && \
    cd ${CESMROOT} && \
    ./bin/git-fleximod update

# Define a cache-busting argument
ARG CACHEBUST=1

# ---- Clone CrocoDash and checkout submodule branch ----
RUN git clone --recurse-submodules https://github.com/CROCODILE-CESM/CrocoDash.git && \
    cd CrocoDash/CrocoDash/rm6 && \
    git fetch origin && \
    git checkout -b s3_zarr origin/s3_zarr

# ---- Clone CrocoGallery ----
RUN git clone https://github.com/CROCODILE-CESM/CrocoGallery.git

# ---- Create conda environment from CrocoDash ----
RUN conda env create -f CrocoDash/environment.yml && \
    conda clean --all --yes

# ---- Install extra Python packages from CrocoGallery ----
SHELL ["conda", "run", "-n", "CrocoDash", "/bin/bash", "-c"]
RUN pip install -r CrocoGallery/requirements.txt

# ---- Activate conda env by default in interactive shells ----
SHELL ["/bin/bash", "-c"]
RUN echo "conda activate CrocoDash" >> ~/.bashrc
