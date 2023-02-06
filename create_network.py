"""
author: Peter Steiglechner
title: batch_simulations.py
content: create in-group and between-group network with small-world properties  
last updated: January 2023
"""
import networkx as nx
import numpy as np
import random
import copy as copy


def create_withinAndBetweenGroup_network(n, k_in, k_out, p, seed):
    assert  (type(n)==int) and (n%2==0)
    # Create in-group networks G1 and G2
    if  (k_in%2==0) and (k_out%2==0):
        G1 = nx.watts_strogatz_graph(int(n/2), k_in, p, seed=seed)
        G2 = nx.watts_strogatz_graph(int(n/2), k_in, p, seed=seed+100)
    else:
        G1 = watts_strogatz_graph_UnevenK(int(n/2), k_in, p, seed=seed)
        G2 = watts_strogatz_graph_UnevenK(int(n/2), k_in, p, seed=seed+100)
    G2 = nx.relabel_nodes(G2, dict(zip(G2.nodes, np.arange(len(G2.nodes))+len(G1.nodes))))
    G = nx.Graph()
    G.add_edges_from(list(G1.edges())+list(G2.edges()))
    G.add_nodes_from(list(G1.nodes())+list(G2.nodes()))
    # connect agents from group 1 to group 2 
    # the ring lattices are stacked on top of each other
    # every agent in group 1 is connected to the corresponding agent in group 2
    which_betweengroup_nodes_to_connect = [0, 1,-1,2,-2,3,-3,4,-4][:int(k_out)] 
    for edgefrom in range(len(G1.nodes)):
        for i in which_betweengroup_nodes_to_connect:
            edgeto = edgefrom  + len(G1.nodes) + i
            # make sure that the indices stay within the bounds
            if edgeto >= n: edgeto -= len(G1.nodes) 
            if edgeto < len(G1.nodes): edgeto += len(G1.nodes)  
            G.add_edge(edgefrom, edgeto)
            # randomly rewire some of these group links
            if np.random.random() < p:
                G.remove_edge(edgefrom, edgeto)
                while True:
                    # select one of the two edges and rewire it to a new node (that is not yet a neighbour or creates a self-loop).              
                    if np.random.random()<0.5:
                        edgetoNew = np.random.choice(G2.nodes)
                        edgefromNew = copy.copy(edgefrom)
                    else:
                        edgefromNew = np.random.choice(G1.nodes)
                        edgetoNew = copy.copy(edgeto)
                    if edgefromNew!=edgetoNew and not G.has_edge(edgefromNew, edgetoNew):
                        G.add_edge(edgefromNew, edgetoNew)
                        break
    social_id_affiliations = dict(enumerate([0 for n in G1.nodes] + [1 for n in G2.nodes]))
    nx.set_node_attributes(G, social_id_affiliations, name="social_identity")
    pos = nx.spring_layout(G)
    return G, pos





# #####################################
# ########### Network #################
# #####################################
def watts_strogatz_graph_UnevenK(n, k, p, seed=None):
    """ 
    WS network that allows to set uneven k. 
    The code is a copy from the networkx.watts_strogatz_graph function 
    extended by code between "NEW" and "END NEW"
    
    Links between nodes n and n+(k+1)/2 are drawn with probability 50% if k is uneven. 
    """
    if k>=n:
        raise nx.NetworkXError("k>=n, choose smaller k or larger n")
    if seed is not None:
        random.seed(seed)

    G = nx.Graph()
    G.name="watts_strogatz_graph(%s,%s,%s)"%(n,k,p)
    nodes = list(range(n)) # nodes are labeled 0 to n-1
    # connect each node to k/2 neighbors
    for j in range(1, k // 2+1):
        targets = nodes[j:] + nodes[0:j] # first j nodes are now last in list
        G.add_edges_from(zip(nodes,targets))
    
    # NEW    
    if k%2==1:
        for m in nodes:
            if random.random()<0.5:
                # connect m to the k//2+1 edge
                oddtarget = nodes[(m+k//2+1)%n]
                G.add_edge(m, oddtarget)
                if np.random.random()<p:
                    # rewire that edge
                    # Enforce no self-loops or multiple edges
                    w = random.choice(nodes)
                    while w == m or G.has_edge(m, w):
                        w = random.choice(nodes)
                        if G.degree(m) >= n-1:
                            break # skip this rewiring
                    else:
                        G.remove_edge(m,oddtarget)
                        G.add_edge(m,w) 
    # END NEW
    #       
    # rewire edges from each node
    # loop over all nodes in order (label) and neighbors in order (distance)
    # no self loops or multiple edges allowed
    for j in range(1, k // 2+1): # outer loop is neighbors
        targets = nodes[j:] + nodes[0:j] # first j nodes are now last in list
        # inner loop in node order
        for u,v in zip(nodes,targets):
            if random.random() < p:
                w = random.choice(nodes)
                # Enforce no self-loops or multiple edges
                while w == u or G.has_edge(u, w):
                    w = random.choice(nodes)
                    if G.degree(u) >= n-1:
                        break # skip this rewiring
                else:
                    G.remove_edge(u,v)
                    G.add_edge(u,w)
    return G
