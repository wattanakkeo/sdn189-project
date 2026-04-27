#!/usr/bin/env python3
# path_splitter.py -- flowspace-based path selection demo for Ryu OF1.3

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp

VIDEO_PORT = 9999  # "high-bandwidth" class selector

# Edge port maps
# s1: host ports 1,2; trunks: to s2=3, to s3=4
# s4: host ports 1,2; trunks: from s2=3, from s3=4
PORTMAP = {
    1: {"hosts": [1, 2], "to_s2": 3, "to_s3": 4},  # s1
    4: {"hosts": [1, 2], "to_s2": 3, "to_s3": 4},  # s4
}


class PathSplitter(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Per-switch MAC learning table: dpid -> {mac -> port}
        self.mac_to_port = {}

    def add_flow(self, dp, priority, match, actions, idle=0, hard=0):
        ofp = dp.ofproto
        p = dp.ofproto_parser
        inst = [p.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        mod = p.OFPFlowMod(
            datapath=dp,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle,
            hard_timeout=hard,
        )
        dp.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp = dp.ofproto
        p = dp.ofproto_parser

        # ARP fast-path (low priority) to avoid controller churn
        self.add_flow(
            dp,
            priority=5,
            match=p.OFPMatch(eth_type=0x0806),  # ARP
            actions=[p.OFPActionOutput(ofp.OFPP_FLOOD)],
        )

        # Table-miss to controller
        self.add_flow(
            dp,
            priority=0,
            match=p.OFPMatch(),
            actions=[p.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)],
        )

        self.logger.info(
            f"switch_features_handler: dpid={dp.id} bootstrap installed"
        )

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        p = dp.ofproto_parser
        dpid = dp.id
        in_port = msg.match.get("in_port")

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        # Learn src MAC
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][eth.src] = in_port

        # Defaults
        out_port = None
        actions = None
        is_video = False

        # If we already know the dst location on this switch, deliver locally
        if eth.dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][eth.dst]

        # Edge classification only on mapped edge switches
        pmap = PORTMAP.get(dpid)
        if pmap:
            # If dst is a local host on the same switch, keep local delivery
            dst_is_local_host = (
                eth.dst in self.mac_to_port[dpid]
                and self.mac_to_port[dpid][eth.dst] in pmap["hosts"]
            )
            src_is_edge_host = in_port in pmap["hosts"]

            # Classify traffic (IPv4/TCP/port=VIDEO_PORT)
            ip4 = pkt.get_protocol(ipv4.ipv4)
            tcpp = pkt.get_protocol(tcp.tcp)
            is_video = bool(
                ip4 and tcpp and (
                    tcpp.src_port == VIDEO_PORT or tcpp.dst_port == VIDEO_PORT
                )
            )

            # Choose trunk only if src is an edge host and dest is non-local
            if src_is_edge_host and not dst_is_local_host:
                chosen = pmap["to_s3"] if is_video else pmap["to_s2"]
                out_port = chosen

                # Install high-priority video rules so learning won't steal it later
                if is_video:
                    for m in (
                        p.OFPMatch(
                            eth_type=0x0800,  # IPv4
                            ip_proto=6,       # TCP
                            in_port=in_port,
                            tcp_src=VIDEO_PORT,
                            eth_dst=eth.dst,
                        ),
                        p.OFPMatch(
                            eth_type=0x0800,
                            ip_proto=6,
                            in_port=in_port,
                            tcp_dst=VIDEO_PORT,
                            eth_dst=eth.dst,
                        ),
                    ):
                        self.add_flow(
                            dp,
                            priority=100,
                            match=m,
                            actions=[p.OFPActionOutput(chosen)],
                            idle=20,
                        )

        # Fallback action selection
        if out_port is None:
            if pmap:
                # Edge switch: flood only to other host ports (avoid blasting trunks)
                host_ports = [hp for hp in pmap["hosts"] if hp != in_port]
                actions = [p.OFPActionOutput(hp) for hp in host_ports] or [
                    p.OFPActionOutput(ofp.OFPP_FLOOD)
                ]
            else:
                # Non-edge (core) switch: generic flood is acceptable
                actions = [p.OFPActionOutput(ofp.OFPP_FLOOD)]
        else:
            actions = [p.OFPActionOutput(out_port)]

        # Install modest-priority L2 learned rule (below video rules)
        match = p.OFPMatch(in_port=in_port, eth_src=eth.src, eth_dst=eth.dst)
        self.add_flow(dp, priority=10, match=match, actions=actions, idle=10)

        # Log decision for teaching/visibility
        try:
            out_ports = [a.port for a in actions if hasattr(a, "port")]
            self.logger.info(
                f"dpid={dpid} in={in_port} dst={eth.dst} video={is_video} -> out={out_ports}"
            )
        except Exception:
            pass

        # Immediate packet out
        out = p.OFPPacketOut(
            datapath=dp,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=None if msg.buffer_id != ofp.OFP_NO_BUFFER else msg.data,
        )
        dp.send_msg(out)
