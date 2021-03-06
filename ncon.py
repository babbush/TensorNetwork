# Copyright 2019 The TensorNetwork Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""NCON interface to TensorNetwork."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from tensornetwork import TensorNetwork


def ncon(tensors, network, con_order=None, out_order=None):
    r"""Contracts a list of tensors according to a tensor network specification.

    The network is provided as a list of lists, one for each
    tensor, specifying labels for the edges connected to that tensor.

    If a contraction order `con_order` and an output order `out_order`
    are both provided, the edge labels can be anything.
    Otherwise (`con_order == None or out_order == None`), the edge labels 
    must be integers and edges will be contracted in ascending order.
    Negative integers denote the (dangling) indices of the output tensor,
    which will be in descending order, e.g. [-1,-2,-3,...].

    For example, matrix multiplication:

    ```python
    A = tf.constant([[1.0, 2.0], [3.0, 4.0]])
    B = tf.constant([[1.0, 1.0], [0.0, 1.0]])
    ncon([A,B], [(-1, 0), (0, -2)])
    ```

    Matrix trace:

    ```python
    A = tf.constant([[1.0, 2.0], [3.0, 4.0]])
    ncon([A], [(0, 0)]) # 5.0
    ```

    Args:
      tensors: List of `Tensor`s.
      network: List of lists specifying the tensor network.
      con_order: List of edge labels specifying the contraction order.
      out_order: List of edge labels specifying the output order.

    Returns:
      A `Tensor` resulting from the contraction of the tensor network.
    """
    tn, con_edges, out_edges = ncon_network(
        tensors, network, con_order=con_order, out_order=out_order)

    # Contract assuming all edges connecting a given pair of nodes are adjacent
    # in con_order. If this is not the case, the contraction is sub-optimal
    # so we throw an exception.
    prev_nodes = []
    while len(con_edges) > 0:
        e = con_edges.pop(0)  # pop so that older nodes can be deallocated
        nodes = e.get_nodes()

        nodes_set = set(nodes)
        if nodes_set != set(prev_nodes):
            if not nodes_set.issubset(tn.nodes_set):
                # the node pair was already contracted
                raise ValueError(
                    "Edge '{}' is not adjacent to other edges connecting "
                    "'{}' and '{}' in the contraction order.".format(
                        e, nodes[0], nodes[1]))
            tn.contract_between(*nodes, name="con({},{})".format(*nodes))
            prev_nodes = nodes

    # TODO: More efficient ordering of products based on out_edges
    res_node = tn.outer_product_final_nodes(out_edges)

    return res_node.tensor


def ncon_network(tensors, network, con_order=None, out_order=None):
    r"""Creates a TensorNetwork from a list of tensors according to `network`.

    The network is provided as a list of lists, one for each
    tensor, specifying labels for the edges connected to that tensor.

    If a contraction order `con_order` and an output order `out_order`
    are both provided, the edge labels can be anything.
    Otherwise (`con_order == None or out_order == None`), the edge labels 
    must be integers and edges will be contracted in ascending order.
    Negative integers denote the (dangling) indices of the output tensor,
    which will be in descending order, e.g. [-1,-2,-3,...].

    This is used internally by `ncon()`.

    Args:
      tensors: List of `Tensor`s.
      network: List of lists specifying the tensor network.
      con_order: List of edge labels specifying the contraction order.
      out_order: List of edge labels specifying the output order.

    Returns:
      net: `TensorNetwork` equivalent to `network`.
      con_edges: List of internal `Edge` objects in contraction order.
      out_edges: List of dangling `Edge` objects in output order.
    """
    if len(tensors) != len(network):
        raise ValueError('len(tensors) != len(network)')

    tn, edges = _build_network(tensors, network)

    if con_order is None:
        con_order = sorted((k for k in edges.keys() if k >= 0))

    if out_order is None:
        out_order = sorted((k for k in edges.keys() if k < 0), reverse=True)

    con_edges = [edges[k] for k in con_order]
    out_edges = [edges[k] for k in out_order]

    for e in con_edges:
        if e.is_dangling():
            raise ValueError(
                "Contraction edge {} appears only once in the network.".format(
                    str(e)
                ))

    for e in out_edges:
        if not e.is_dangling():
            raise ValueError(
                "Output edge {} appears more than once in the network.".format(
                    str(e)
                ))

    return tn, con_edges, out_edges


def _build_network(tensors, network):
    tn = TensorNetwork()
    nodes = []
    edges = {}
    for (i, (tensor, edge_lbls)) in enumerate(zip(tensors, network)):
        if len(tensor.shape) != len(edge_lbls):
            raise ValueError(
                "Incorrect number of edge labels specified tensor {}".format(i)
            )

        node = tn.add_node(tensor, name="tensor_{}".format(i))
        nodes.append(node)

        for (axis_num, edge_lbl) in enumerate(edge_lbls):
            if edge_lbl not in edges:
                e = node[axis_num]
                e.set_name(str(edge_lbl))
                edges[edge_lbl] = e
            else:
                # This will raise an error if the edges are not dangling.
                e = tn.connect(
                    edges[edge_lbl],
                    node[axis_num],
                    name=str(edge_lbl))
                edges[edge_lbl] = e
    return tn, edges
