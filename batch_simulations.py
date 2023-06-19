"""
author: Peter Steiglechner
title: batch_simulations.py
content: functions to perform ensemble runs. Needs OpinionModel class from model.py
last updated: January 2023
"""
import xarray as xr
import numpy as np
import multiprocessing as mp
import time
from model import *
from batch_simulations import *
import sys
import os

def save_batch(m):
    """ save model variables and attributes into ncdf file """
    data_vars = dict(
                avg_mean_ops=(["seed", "time", "ain", "aout"], np.array([m.avg_mean_ops[str(t)] for t in m.stored_times]).reshape(1,len(m.stored_times), 1, 1)),
                std_mean_ops=(["seed", "time", "ain", "aout"], np.array([m.std_mean_ops[str(t)] for t in m.stored_times]).reshape(1,len(m.stored_times),1,1)),
                consensus_time=(["seed", "ain", "aout"], np.array([m.consensus_time]).reshape(1,1,1)),
                consensus_mean=(["seed", "ain", "aout"], np.array([m.consensus_mean]).reshape(1,1,1)),
            )
    coords = dict(
                time=m.stored_times, 
                seed=[m.seed],
                ain=[m.alpha_in],
                aout=[m.alpha_out]
            )
    if m.agent_reporter:
        data_vars["mean_op"] = (["seed", "time", "AgentID", "ain", "aout"], np.array([m.all_mean_ops[str(t)] for t in m.stored_times]).reshape(1,len(m.stored_times), m.n_agents,1,1))
        data_vars["sig"] = (["seed", "time", "AgentID", "ain", "aout"], np.array([m.all_sigs[str(t)] for t in m.stored_times]).reshape(1,len(m.stored_times), m.n_agents,1,1))
        coords["AgentID"] =np.arange(m.n_agents)

    
    ds = xr.Dataset(
            data_vars=data_vars,
            coords=coords,
            attrs=dict(social_id_groups=m.social_id_groups),
        )
    for att in ["n_agents", "k", "k_in", "k_out", "p_rewire", "sig_op_0","communication_frequency", "kappa", "delta_0", "sigma_threshold_consensus"]:
        ds.attrs[att] = eval("m."+att)
    return ds



def perform_one_run(modelclass, settings, seed, agent_reporter=False):
    #folder, n_agents, k, a_ins, a_outs, sig_op_0, communication_frequency, kappa, delta_0, track_times, p_rewire = settings
    folder = settings["folder"]
    a_ins = settings["a_ins"]
    a_outs = settings["a_outs"]
    params = {
                "n_agents": settings["n_agents"],
                "social_id_groups": [0, 1],
                "k": settings["k"],  
                "k_in": settings["k_in"],  
                "k_out": settings["k_out"],  
                "alpha_in": None,
                "alpha_out": None,
                "sig_op_0": settings["sig_op_0"],
                "communication_frequency":  settings["communication_frequency"],
                "kappa": settings["kappa"],
                "delta_0": settings["delta_0"],
                "p_rewire": settings["p_rewire"],
                "seed": seed,
            }
    fnameBase = f"ms1_WS{params['p_rewire']}_n{params['n_agents']}_k-{params['k']}"+\
        f"_kin-{params['k_in']}_kout-{params['k_out']}_sig-{params['sig_op_0']}"+\
        f"_commf-{params['communication_frequency']}_kappa-{params['kappa']}_delta-{params['delta_0']}"
    for n, ain in enumerate(a_ins):
        fullname = folder+fnameBase+"_ain{}_seed-{}.ncdf".format(ain, seed)
        if not os.path.exists(fullname):
            m_ds_arr = None
            for aout in a_outs[:n+1]:
                #print("Running ain,aout={},{}".format(ain, aout))
                params["alpha_in"] = ain
                params["alpha_out"] = aout
                m = modelclass(params, agent_reporter=agent_reporter, track_times=settings["track_times"])
                m.simulation()
                m_ds = save_batch(m)
                if m_ds_arr is None:
                    m_ds_arr = m_ds
                else:
                    m_ds_arr = xr.merge([m_ds_arr, m_ds])
            m_ds_arr.to_netcdf(fullname)
    return  fullname


if __name__=="__main__":
    #import os.path
    #fname = 
    #if not os.path.isfile(finalSetting[folder+):
    s0 = time.time()
    # print(sys.argv)

    n_agents = int(sys.argv[1])
    k  = float(sys.argv[2])
    k_in = int(sys.argv[3])
    k_out = int(sys.argv[4])
    delta_0 = float(sys.argv[5])
    kappa = float(sys.argv[6]) 
    communication_frequency = float(sys.argv[7]) 
    sig_op_0 = float(sys.argv[8]) 
    p_rewire = float(sys.argv[9])
    T = int(sys.argv[10])    
    resolution = sys.argv[11] 
    seed = int(sys.argv[12])

    step=100 if T<=1000 else min(5000, int(T/10))
    track_times = np.arange(0,T+1, step=step)

    if resolution =="high":
        a_ins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.99]
        a_outs = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.99]
    elif resolution =="low":
        a_ins = [0.25, 0.5, 0.75]
        a_outs = [0.25, 0.5, 0.75]

    folder = "data/"
    #if not os.path.exists(folder):
    #    os.mkdir(folder)

    finalSetting = dict(
        folder=folder, 
        n_agents=n_agents, 
        k=k, 
        k_in = k_in,
        k_out = k_out,
        a_ins=a_ins, 
        a_outs=a_outs, 
        sig_op_0=sig_op_0, 
        communication_frequency=communication_frequency, 
        kappa=kappa, 
        delta_0=delta_0, 
        track_times=track_times, 
        p_rewire=p_rewire
    )

    #print("CPU units: ", mp.cpu_count(), " using ", min(mp.cpu_count(), 32))
    #with mp.Pool(processes=min(mp.cpu_count(), 32)) as p:
    #    results = p.map(experiment, seeds)
    results = perform_one_run(OpinionModel, finalSetting, seed, agent_reporter=False)
    s1 = time.time()
    print("{} min {} sec".format(int((s1-s0)/60), int(s1-s0)%60 ))
