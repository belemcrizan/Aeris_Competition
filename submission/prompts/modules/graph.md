# Graph navigation

The repository has a static call and dependency graph whose nodes are fully qualified symbols. Node ids follow the module path: function f in pkg/sub/mod.py is pkg.sub.mod.f and a method is pkg.sub.mod.Class.method. The navigation skill script locate_symbol.py maps node ids back to file paths and line ranges.

- get_code_neighbors(node, edge_type, max_neighbors) lists incoming edges (callers, importers) and outgoing edges (callees) of one symbol. Leave edge_type empty unless you need one relation such as calls.
- get_code_subgraph(nodes) returns the edges among a list of symbols. Use it to see how candidate symbols connect.

Policy:

- Expand only from your best one to three candidate symbols. Use max_neighbors between 10 and 20. Go at most two hops from a candidate; never expand every neighbor.
- Follow callers to connect the public API named in the issue to the implementation. Follow callees to find where the wrong value is actually produced.
- Use get_code_subgraph on at most eight symbols to choose the node that lies on the path between the API the issue uses and the faulty behavior.
- Prefer symbols on that path whose code handles the specific case in the issue over generic helpers used everywhere.
- The graph comes from static analysis. Dynamic dispatch, decorators, getattr and registries may be missing. If the graph is empty or unhelpful, fall back to grep instead of retrying the graph.
- Do not call a graph tool twice with the same arguments.
