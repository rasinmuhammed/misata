from typing import List, Dict, Callable, Optional, Any
import networkx as nx # type: ignore
import numpy as np

class CausalNode:
    """
    Represents a variable in the Causal Graph.
    """
    def __init__(
        self, 
        name: str, 
        node_type: str = "endogenous", # 'exogenous' or 'endogenous'
        mechanism: Optional[Callable] = None,
        parents: List[str] = None
    ):
        self.name = name
        self.node_type = node_type # exogenous (root) or endogenous (derived)
        self.mechanism = mechanism # Function that takes parent values and returns node value
        self.parents = parents or []
        self.current_value: Optional[np.ndarray] = None

class CausalGraph:
    """
    Manages the DAG structure and execution order.
    """
    def __init__(self):
        self.graph = nx.DiGraph()
        self.nodes: Dict[str, CausalNode] = {}

    def add_node(self, node: CausalNode):
        self.nodes[node.name] = node
        self.graph.add_node(node.name)
        for parent in node.parents:
            self.graph.add_edge(parent, node.name)

    def get_topological_sort(self) -> List[str]:
        """Returns execution order"""
        return list(nx.topological_sort(self.graph))

    def forward_pass(self, inputs: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """
        Computes values for all nodes given inputs for exogenous nodes.
        """
        results = inputs.copy()
        execution_order = self.get_topological_sort()

        for node_name in execution_order:
            node = self.nodes[node_name]
            
            # Skip if already provided in inputs (exogenous)
            if node_name in results:
                continue
                
            # Gather parent values
            parent_values = [results[p] for p in node.parents]
            
            # Execute mechanism
            if node.mechanism:
                results[node_name] = node.mechanism(*parent_values)
            else:
                raise ValueError(f"Node {node_name} has no inputs and no mechanism!")
                
        return results

def saas_mechanism_leads(traffic, conversion_rate):
    return traffic * conversion_rate

def saas_mechanism_deals(leads, sales_conversion):
    return leads * sales_conversion

def saas_mechanism_revenue(deals, aov):
    return deals * aov

def get_saas_template() -> CausalGraph:
    """
    Returns a standard SaaS Causal Graph:
    Traffic -> Leads -> Deals -> Revenue
    """
    cg = CausalGraph()

    # Exogenous (Root Nodes)
    cg.add_node(CausalNode("Traffic", "exogenous"))
    cg.add_node(CausalNode("LeadConversion", "exogenous"))
    cg.add_node(CausalNode("SalesConversion", "exogenous"))
    cg.add_node(CausalNode("AOV", "exogenous")) # Average Order Value

    # Endogenous (Derived Nodes)
    cg.add_node(CausalNode(
        "Leads", 
        "endogenous", 
        mechanism=saas_mechanism_leads,
        parents=["Traffic", "LeadConversion"]
    ))
    
    cg.add_node(CausalNode(
        "Deals", 
        "endogenous", 
        mechanism=saas_mechanism_deals,
        parents=["Leads", "SalesConversion"]
    ))

    cg.add_node(CausalNode(
        "Revenue", 
        "endogenous", 
        mechanism=saas_mechanism_revenue,
        parents=["Deals", "AOV"]
    ))

    return cg
