"""
Convert the nodes and server-instances in default.xml to a multi-node
configuration

The configuration string should be in the form node1:s1,s2,... node2:s3 ...

Examples

Everything on a single node (default, the same as passing no config):
master:Blitz-0,Indexer-0,DropBox,MonitorServer,FileServer,Storm,PixelData-0,Processor-0,Tables-0,TestDropBox

Processor on a separate node:
master:Blitz-0,Indexer-0,DropBox,MonitorServer,FileServer,Storm,PixelData-0,Tables-0,TestDropBox slave:Processor-0

Two Processor and two PixelData on two separate nodes:
master:Blitz-0,Indexer-0,DropBox,MonitorServer,FileServer,Storm,Tables-0,TestDropBox slave-1:Processor-0,PixelData-0 slave-2:Processor-1,PixelData-1
"""


import re
import sys


def _getnodes(nodedescs):
    nodes = {}
    for nd in nodedescs:
        s = ''
        node, descs = nd.split(':')
        descs = descs.split(',')
        for d in descs:
            try:
                t, i = d.split('-')
            except ValueError:
                t = d
                i = None
            s += '      <server-instance template="%sTemplate"' % t
            if i is not None:
                s += ' index="%s"' % i
            if t in ('Blitz',):
                s += ' config="default"'
            if t in ('PixelData', 'Processor', 'Tables'):
                s += ' dir=""'
            s += '/>\n'
        nodes[node] = s
    return nodes


def _process_xml(xml, nodedescs):
    pattern = r'\<node name="master"\>\s*\<server-instance[^\>]*\>(.*?\</node\>)'
    m = re.search(pattern, xml, re.DOTALL)
    assert m

    master = '\n    </node>\n'
    slaves = ''
    nodes = _getnodes(nodedescs.split())
    for nodename in sorted(nodes.keys()):
        servers = nodes[nodename]
        if nodename == 'master':
            master = '%s%s' % (servers, master)
        else:
            slaves += '    <node name="%s">\n%s    </node>\n' % (nodename, servers)

    if nodes:
        xmlout = xml[:m.start(1)] + master + slaves + xml[m.end(1):]
    else:
        xmlout = xml
    return xmlout
