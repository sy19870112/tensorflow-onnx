# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT license.

"""Identity Optimizer.
   Remove useless Identity node in graphs including subgraphs, but does not hurt model output names.
"""

from __future__ import unicode_literals

from tf2onnx.optimizer.optimizer_base import GraphOptimizerBase

# pylint: disable=logging-not-lazy,unused-argument,missing-docstring,unused-variable,arguments-differ


class IdentityOptimizer(GraphOptimizerBase):
    """Identity Optimizer."""

    def __init__(self, debug=False):
        super(IdentityOptimizer, self).__init__("IdentityOptimizer", debug)
        self._g = None

    def optimize(self, graph):
        self._g = graph
        previous_counter = self._g.dump_node_statistics()
        self._optimize_recursively(self._g)
        current_counter = self._g.dump_node_statistics()
        identity_cnt = current_counter["Identity"]
        self.log.info(" %d identity op(s) left", identity_cnt)
        self._print_stat_diff(previous_counter, current_counter)
        return self._g

    def _optimize_recursively(self, g):
        self._optimize(g)
        nodes = [n for n in g.get_nodes()]
        for n in nodes:
            body_graphs = n.get_body_graphs()
            if body_graphs:
                for attr, b_g in body_graphs.items():
                    self.log.debug("start handling subgraph of %s's attribute %s", n.name, attr)
                    self._optimize_recursively(b_g)
                    self.log.debug("finish handling subgraph of %s's attribute %s", n.name, attr)

    def _optimize(self, g):
        has_update = True
        while has_update:
            has_update = False
            nodes = [n for n in g.get_nodes() if n.type == "Identity"]
            for n in nodes:
                if n.graph is None:
                    self.log.info("node has been removed from this graph, skip")
                    continue

                graph_outputs = set(n.output).intersection(g.outputs)
                ret = False
                if graph_outputs:
                    ret = self._handle_graph_output_identity(g, n, graph_outputs)
                else:
                    ret = self._handle_non_graph_output_identity(g, n)
                has_update = ret

        self._g.topological_sort(self._g.get_nodes())

    @staticmethod
    def _handle_non_graph_output_identity(graph, identity):
        graph.replace_all_inputs(graph.get_nodes(), identity.output[0], identity.input[0])
        graph.remove_node(identity.name)
        return True

    def _handle_graph_output_identity(self, graph, identity, graph_outputs):
        input_id = identity.input[0]
        input_node = identity.inputs[0]

        if input_node.graph != graph:
            # If input node is in parent graph, we don't handle it now
            self.log.debug("input node in parent graph, skip")
            return False

        if input_node.is_graph_input():
            # Identity between input and output should not be removed.
            self.log.debug("skip identity between input and output")
            return False

        output_id = identity.output[0]
        output_shape = graph.get_shape(output_id)
        output_dtype = graph.get_dtype(output_id)
        if input_id in graph.outputs:
            # input id already be graph output, so we cannot make that be another graph output.
            # this Identity must be kept.
            self.log.debug("identity input already be graph output")
            return False

        graph.remove_node(identity.name)
        new_output = [output_id if o == input_id else o for o in input_node.output]
        input_node.output = new_output

        graph.set_shape(output_id, output_shape)
        graph.set_dtype(output_id, output_dtype)

        graph.replace_all_inputs(graph.get_nodes(), input_id, output_id)
        return True
