import heapq

class ShortestPath(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'switches': topo_switches.Switches}

 # Dijkstra
    def dijkstra(self, src_dpid):
        """Return (dist, prev) dicts for shortest hop-count paths from src_dpid."""
        dist = {dpid: float('inf') for dpid in self.datapaths}
        prev = {dpid: None for dpid in self.datapaths}
        dist[src_dpid] = 0
        # min-heap: (cost, dpid)
        heap = [(0, src_dpid)]

        while heap:
            cost, u = heapq.heappop(heap)
            if cost > dist[u]:
                continue
            for (a, b), _port in self.adjacency.items():
                if a != u:
                    continue
                new_cost = dist[u] + 1  # uniform hop cost
                if new_cost < dist[b]:
                    dist[b] = new_cost
                    prev[b] = u
                    heapq.heappush(heap, (new_cost, b))

        return dist, prev

    def get_path(self, src_dpid, dst_dpid):
        """Return ordered list of dpids from src to dst, or [] if unreachable."""
        if src_dpid not in self.datapaths or dst_dpid not in self.datapaths:
            return []
        _dist, prev = self.dijkstra(src_dpid)
        path = []
        node = dst_dpid
        while node is not None:
            path.append(node)
            node = prev[node]
        path.reverse()
        if path and path[0] == src_dpid:
            return path
        return []