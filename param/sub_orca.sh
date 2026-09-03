#!/bin/bash
#BSUB -J orca
#BSUB -n 56
#BSUB -q normal
#BSUB -R 'span[ptile=56]'
#BSUB -o %J

ulimit -s unlimited
source /data/home/miwenhui/soft/orca.sh
# file_name=$(basename "$1" .inp)
/data/home/miwenhui/soft/orca_6_1_0_avx2/orca test.inp > "orca.log" 2>&1
