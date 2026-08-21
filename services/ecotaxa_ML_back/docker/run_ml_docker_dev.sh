#!/bin/bash
# Note: mount your local directories according to the config.ini needs
docker run --rm --gpus all --security-opt seccomp=unconfined \
-u 1000:1000 --name ecotaxagpuback  \
--mount type=bind,source=${PWD}/../src/config.ini,target=/config.ini  \
--mount type=bind,source=/vieux,target=/vieux  \
--mount type=bind,source=/home/laurent/Devs/ecotaxa/models,target=/home/laurent/Devs/ecotaxa/models \
local/ecotaxa_ml_back

