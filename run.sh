#!/bin/bash

. /opt/conda/etc/profile.d/conda.sh

conda activate phd1

export n=$1
export k=$2
export h=$3
export delta=$4
export kappa=$5
export commf=$6
export sig=$7
export p_rewire=$8
export T=$9
export resolution=${10}
export seed=${11}

echo "$n $k $h $delta $kappa $commf $sig $p_rewire $T $resolution $seed"

python3 batch_simulations.py $n $k $h $delta $kappa $commf $sig $p_rewire $T $resolution $seed 

echo "finished"
