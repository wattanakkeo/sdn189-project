#!/usr/bin/env python3
from mininet.topo import Topo
class FVTopo(Topo):
	"""
Diamond topology for slicing labs.
h1 h2
\ /
s1
/ \
(low) (high)
s2 s3
\ /
s4
/ \
h3 h4
- s1<->s2 and s2<->s4 are low bandwidth (e.g., 1 Mbps)
- s1<->s3 and s3<->s4 are high bandwidth (e.g., 10 Mbps)
"""
	def build(self, low_bw=1, high_bw=10, delay='2ms', loss=0):
# switches
		s1 = self.addSwitch('s1')
		s2 = self.addSwitch('s2')
		s3 = self.addSwitch('s3')	
		s4 = self.addSwitch('s4')
# hosts
		h1 = self.addHost('h1', ip='10.0.0.1/24')
		h2 = self.addHost('h2', ip='10.0.0.2/24')
		h3 = self.addHost('h3', ip='10.0.0.3/24')
		h4 = self.addHost('h4', ip='10.0.0.4/24')
# host -> edge switch links (default params)
		self.addLink(h1, s1)
		self.addLink(h2, s1)
		self.addLink(h3, s4)
		self.addLink(h4, s4)
	# core links with tc params
	# low-bandwidth path via s2
		self.addLink(s1, s2, bw=low_bw, delay=delay, loss=loss, use_htb=True)
		self.addLink(s2, s4, bw=low_bw, delay=delay, loss=loss, use_htb=True)
	# high-bandwidth path via s3
		self.addLink(s1, s3, bw=high_bw, delay=delay, loss=loss, use_htb=True)
		self.addLink(s3, s4, bw=high_bw, delay=delay, loss=loss, use_htb=True)
topos = {'fvtopo': FVTopo}
