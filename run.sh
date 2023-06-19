#!/bin/bash

. /opt/conda/etc/profile.d/conda.sh

conda activate phd1

export n=$1
export k=$2
export kin=$3
export kout=$4
export delta=$5
export kappa=$6
export commf=$7
export sig=$8
export p_rewire=$9
export T=${10}
export resolution=${11}
export seed=${12}

echo "$n $k $kin $kout $delta $kappa $commf $sig $p_rewire $T $resolution $seed"

python3 batch_simulations.py $n $k $kin $kout $delta $kappa $commf $sig $p_rewire $T $resolution $seed 

echo "finished"
