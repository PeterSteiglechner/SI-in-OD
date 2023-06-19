"""
author: Peter Steiglechner
title: model.py
project: in-group favouritism bias in opinion formation.
last updated: June 2023
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
import networkx as nx
import scipy.stats as stats
import sys
import matplotlib as mpl
import os
import time
import random
import copy
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

from create_network import *
from batch_simulations import *


# ############################################
# ########    MODEL and AGENT    #############
# ############################################

class OpinionModel():
    """"
    Model of opinion formation with in-group bias and homophily
    """

    def __init__(self, _params, agent_reporter=True, track_times=None):
        """
        Initialise the model. 
        Arguments: 
            -  _params: dictionary with the following keys 
        	    - "social_id_groups" (list of ints), 
                - "n_agents" (int), 
                - "alpha_in" (float), 
                - "alpha_out" (float), 
                - "k" (float), 
                - "p_rewire" (float),
                - "k_in" (int), 
                - "k_out" (int), 
                - "sig_op_0" (float), 
                - "communication_frequency" (float), 
                - "kappa" (float), 
                - "delta_0" (float), 
                - "seed" (int)
            - agent_reporter (boolean):   
                whether agent-level data should be tracked or not
            - track_times: list of ints:   the times at which the system/agent states are tracked
        """

        self.n_agents = _params["n_agents"]                     # Nr agents
        self.social_id_groups = _params["social_id_groups"]     # names of the social identity groups, for S=2: [0,1]
        self.alpha_in = _params["alpha_in"]                     # in-group filter transparency
        self.alpha_out = _params["alpha_out"]                   # out-group filter transparency
        self.k = _params["k"]                                   # avg node degree per agent
        self.p_rewire = _params["p_rewire"]                     # rewiring probability for network links 
        self.k_in = _params["k_in"]                                   # degree of homophily in the network between 0 and 1
        self.k_out = _params["k_out"]                                   # degree of homophily in the network between 0 and 1
        self.sig_op_0 = _params["sig_op_0"]                     # variance of (gaussian) initial opinions
        self.communication_frequency = _params["communication_frequency"]         # interaction frequency f
        self.kappa = _params["kappa"]                           # diffusion constant
        self.delta_0 = _params["delta_0"]                       # predisposition of agent opinions
        self.seed = _params["seed"]                             

        self.agent_reporter = agent_reporter
        self.track_times = track_times
        self.sigma_threshold_consensus = 0.01                   # dispersion threshold for consensus 

        # ==== Create the opinion space ====
        # create a belief space B with 200 statements (and bins around them) between -1 and 1
        n_beliefs = 200
        belief_space_bounds = np.linspace(-1, 1, n_beliefs + 1, endpoint=True)              # -1,   -0.99,  -0.98, ..., 0.99,   1
        self.belief_space = belief_space_bounds[:-1] + np.diff(belief_space_bounds) / 2     # -0.995,  -0.985, ....    0.995
        self.db = (belief_space_bounds[-1] - belief_space_bounds[0]) / n_beliefs            # 0.01
        self.uniform = np.ones(n_beliefs) / (n_beliefs * self.db)                           # uniform distribution over the belief space


        # ==== Create matrix for calculating the diffusion equation/ heat equation ====
        # heat equation:
        #   $$ \frac{d}{dt} x(b,t) = \kappa \cdot \frac{\del^2}{\del b^2} x(b,t) $$
        # use backward time, central difference scheme:
        #   $$ \frac{x(b, t+1) - x(b, t)}{\Delta t} = \kappa  \cdot \frac{ x(b+1, t+1) + x(b-1, t+1) - 2 x(b, t+1)}{\Delta b^2}
        #      x(b, t) = x(b, t+1) - \Delta t \kappa/\Delta b^2 \cdot ( x(b+1, t+1) + x(b-1, t+1) - 2 x(b, t+1) )
        #      x(t) = A \cdot x(t+1)  +  {\rm Dirichlet\ Boundaries}
        #      x(t+1) = A^{-1} \cdot  x(t)  +  {\rm Dirichlet Boundaries}
        #   $$
        # create the matrix for the backward central difference scheme:            
        # A = 1 + \Delta t \kappa / \Delta b^2 \cdot \begin{cases} 
        #                                               2  & -1 & 0  & 0  & \ldots \\
        #                                               -1 &  2 & -1 & 0  & \ldots \\  
        #                                               0  & -1 & 2  & -1 & \ldots 
        #                                            \end{cases}
        # see e.g. Olsen-Kettle, L. (2011). Numerical solution of partial differential equations. Lecture notes at University of Queensland, Australia. https://espace.library.uq.edu.au/view/UQ:239427
        dt = 1           # time step to solve the diffusion equation
        # A = diagonal + upper off-diag + lower off-diag
        mat_heat_equation = (
            np.diag(np.ones(n_beliefs)) * (1 + 2 * dt * self.kappa / (self.db ** 2)) + \
            np.diag(np.ones(n_beliefs - 1), k=1) * (-1) * dt * self.kappa / (self.db ** 2) + \
            np.diag(np.ones(n_beliefs - 1), k=-1) * \
            (-1) * dt * self.kappa / (self.db ** 2)
        )
        # inverted matrix A^-1
        self.mat_heat_equ_inv = np.linalg.inv(mat_heat_equation)

        # ==== Create Social Ids and Network ====
        np.random.seed(self.seed)
        # calculate avg within and between group link numbers from average node degree $k$ and homophily $h$
        # in earlier versions, a degree of homophily h was defined: and self.k_out = (1-self.h)/2 * self.k; self.k_in = (1+self.h)/2 * self.k
        assert ((self.k_out + self.k_in) == self.k)
        assert (self.n_agents % len(self.social_id_groups) == 0)
        group_size = int(self.n_agents/len(self.social_id_groups))
        self.G, self.pos = create_withinAndBetweenGroup_network(
            self.n_agents,
            self.k_in,
            self.k_out,
            self.p_rewire,
            self.seed
        )
        self.social_id_affiliations = dict(enumerate([[id for ag in range(group_size)] for id in self.social_id_groups]))
        self.adj_mat = nx.adjacency_matrix(self.G)
        nx.set_node_attributes(self.G, self.social_id_affiliations, name="social_identity")
        # for plotting purposes: node positions on the network
        self.pos = nx.spring_layout(self.G)

        # ==== Create agents ====
        self.schedule = []
        for i, n in enumerate(self.G.nodes()):
            social_id = self.G.nodes[i]["social_identity"]
            # draw mean of gaussian initial opinion, $\mu_{i,0}$, for agent i
            # draw positive sign with probability $0.5 + \delta_0 / 2$ for group 1 and $0.5 - \delta_0 / 2$ for group 2 
            if social_id == 0:
                positiveInitialMu = np.random.random() < (0.5 + self.delta_0/2)
            else:
                positiveInitialMu = np.random.random() < (0.5 - self.delta_0/2)
            mu_0 = np.random.random() if positiveInitialMu else -np.random.random()
            # create initial opinion distribution as truncated normal distribution
            sig = self.sig_op_0
            op = stats.norm(loc=mu_0, scale=sig).pdf(self.belief_space)
            op_normed = op / (op.sum() * self.db)
            # create agent
            ag = Agent(self, i, social_id, self.pos[i], op_dist=op_normed)
            # add agent to scheduler
            self.schedule.append(ag)

        # === Data Collection ===
        # collect all "mean_op" (= "agent votes")
        self.all_mean_ops = {"0": np.array([ag.mean_op for ag in self.schedule])}
        if self.agent_reporter:
            self.all_sigs = {"0": np.array([ag.sig for ag in self.schedule])}
        self.avg_mean_ops = {"0": np.mean(self.all_mean_ops["0"])}
        self.std_mean_ops = np.std(self.all_mean_ops["0"])
        self.all_std_mean_op = {"0": np.std(self.all_mean_ops["0"])}

        # tau, the time at which the society has reached consensus (default np.nan)
        self.consensus_time = np.nan
        self.consensus_mean = np.nan

        self.running = True
        self.time = 0
        self.observe()
        self.stored_times = [0]
        return

    def step(self):
        """ update all agents once in random order and observe at specified time steps """
        update_order = np.random.choice(self.schedule, size=self.n_agents, replace=False)
        for ag in update_order:
            ag.step()
        self.time += 1.0
        # calc standard deviation every time step to get precise consensus time
        self.std_mean_ops = np.std([ag.mean_op for ag in self.schedule])
        if self.time in self.track_times:
            self.observe()
            self.stored_times.append(self.time)
        return

    def observe(self):
        """store the mean and standard deviation of the mean opinions of all agents"""
        curr_mean_ops = np.array([ag.mean_op for ag in self.schedule])      # all agent mean opinions 
        self.avg_mean_ops[str(self.time)] = np.mean(curr_mean_ops)      
        self.std_mean_ops[str(self.time)] = np.std(curr_mean_ops)        # dispersion

        if self.agent_reporter:
            # store also agent states
            self.all_ops[str(self.time)] = curr_mean_ops
            self.all_sigs[str(self.time)] = np.array([ag.sig for ag in self.schedule])
        return

    def simulation(self):
        """ perform a model run """
        time_cons = []  # times at which there is consensus
        for t in range(self.track_times[-1]):
            self.step()
            if self.std_mean_ops < self.sigma_threshold_consensus:
                # add current time step to consensus times
                time_cons.append(t)
            if len(time_cons) > 20:
                # stop the simulation after 20 time steps with consensus, 
                # then store consensus time, which is the first time at which consensus occurred
                self.consensus_time = time_cons[0]
                curr_mean_ops = np.array([ag.mean_op for ag in self.schedule]) 
                self.consensus_mean = np.mean(curr_mean_ops)
                if not self.agent_reporter:
                    break
        return


class Agent():
    def __init__(self, model, unique_id, social_identity, xy, op_dist):
        """
        initialise an agent with:
        - a reference to the model
        - a unique id within the model: int
        - a social identity: int
        - a position xy in network (for plotting): list of two floats 
        - an opinion distribution: array of floats with length len(model.belief_space) 

        calculate the agent's mean opinion  and its opinion uncertainty.
        """
        self.model = model
        self.unique_id = unique_id
        self.pos = xy
        self.social_identity = social_identity
        self.op = op_dist

        # calculate mean_op and sigma
        self.mean_op = np.dot(self.op, self.model.belief_space) / self.op.sum()
        var = np.dot(self.op, self.model.belief_space ** 2) / self.op.sum() - self.mean_op ** 2
        self.sig = var ** 0.5 if var > 0 else sys.float_info.epsilon

        # assign parameters from the model
        # so far, all parameters are homogeneous (equal for all agents)
        self.alpha_in = self.model.alpha_in         # in-group perception
        self.alpha_out = self.model.alpha_out       # out-group perception
        self.kappa = self.model.kappa           # diffusion strength during non-interaction
        self.communication_frequency = self.model.communication_frequency   

        self.nbs = list(self.model.G.neighbors(self.unique_id))     # neighbours in (fixed) network
        return

    def step(self):
        """
        Update the agent's opinion via (1) communication (with prob communication_frequency) or (2) diffusion
        """
        if np.random.random() < self.communication_frequency:
            # social interaction (if the agent has a neighbour)
            if len(self.nbs) == 0:
                if self.model.time == 1:
                    print("Network not connected (id={})".format(self.unique_id))
                return
            else:
                self.update_opinion_in_interaction()
        else:
            self.update_opinion_in_non_interaction()

    def update_opinion_in_interaction(self):
        # select one of the neighbours --> agent j
        speaker_id = np.random.choice(self.nbs)
        speaker = self.model.schedule[speaker_id]
        # agent j expresses its opinion
        message = speaker.op
        # perceive the received message
        alpha = self.alpha_in if speaker.social_identity == self.social_identity else self.alpha_out
        perceived_message = alpha * message + (1 - alpha) * self.model.uniform
        posterior_op = self.op * perceived_message
        if posterior_op.sum() < sys.float_info.epsilon:
            # posterior and perceived message are incompatible
            # normalisation will fail. This can happen when alpha=1
            # solution: agent keeps old opinion
            posterior_op = self.op
            print("{} has posterior_op=0.".format(self.unique_id), end=", ")
        self.op = posterior_op / (posterior_op.sum() * self.model.db)
        # calculate mean_op and sigma
        self.mean_op = np.dot(self.op, self.model.belief_space) / self.op.sum()
        var = np.dot(self.op, self.model.belief_space ** 2) / self.op.sum() - self.mean_op ** 2
        self.sig = var ** 0.5 if var > 0 else sys.float_info.epsilon
        return

    def update_opinion_in_non_interaction(self):
        """
        during non-interation, the opinion distribution diffuses slowly
        """
        # solve 1D heat equation (using the A^-1 matrix from backward implicit Euler scheme defined above)
        diffused_op = np.dot(self.model.mat_heat_equ_inv, self.op)
        self.op = diffused_op / (diffused_op.sum() * self.model.db)
        # calculate mean_opinion and sigma
        self.mean_op = np.dot(self.op, self.model.belief_space) / self.op.sum()
        var = np.dot(self.op, self.model.belief_space ** 2) / self.op.sum() - self.mean_op ** 2
        self.sig = var ** 0.5 if var > 0 else sys.float_info.epsilon
        return


if __name__ == "__main__":
    """
    Arguments should be
    python model.py 
    """
    for seed in [2]:
        print(f"running seed {seed}")
        s0 = time.time()
        settings = dict(
            folder="", 
            n_agents=100, 
            k=10, 
            k_in=8,
            k_out=2,
            a_ins=[0.25, 0.5, 0.75], 
            a_outs=[0.25, 0.5, 0.75], 
            sig_op_0=0.2, 
            communication_frequency=0.2, 
            kappa=0.0002, 
            delta_0=0.0, 
            track_times=np.arange(0,3001, 1), 
            p_rewire=0.0
            )
        name = perform_one_run(OpinionModel, settings, seed, agent_reporter=True)
        results = xr.open_dataset(name, engine="netcdf4")
        print(results)
        print("Consensus reached at: ", results.consensus_time.values)

        s1 = time.time()
        print("{} min {} sec".format(int((s1-s0)/60), int(s1-s0) % 60))
