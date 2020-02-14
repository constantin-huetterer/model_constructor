# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/04_Net.ipynb (unless otherwise specified).

__all__ = ['init_cnn', 'act_fn', 'ResBlock', 'NewResBlock', 'Net', 'me', 'xresnet50']

# Cell
import torch.nn as nn
import sys, torch
from functools import partial
from collections import OrderedDict

from .layers import *

# Cell
act_fn = nn.ReLU(inplace=True)

def init_cnn(m):
    if getattr(m, 'bias', None) is not None: nn.init.constant_(m.bias, 0)
    if isinstance(m, (nn.Conv2d,nn.Linear)): nn.init.kaiming_normal_(m.weight)
    for l in m.children(): init_cnn(l)


# Cell
class ResBlock(nn.Module):
    def __init__(self, expansion, ni, nh, stride=1,
                 conv_layer=ConvLayer, act_fn=act_fn, zero_bn=True,
                 pool=nn.AvgPool2d(2, ceil_mode=True), sa=False,sym=False):
        super().__init__()
        nf,ni = nh*expansion,ni*expansion
        layers  = [(f"conv_0", conv_layer(ni, nh, 3, stride=stride, act_fn=act_fn)),
                   (f"conv_1", conv_layer(nh, nf, 3, zero_bn=zero_bn, act=False))
        ] if expansion == 1 else [
                   (f"conv_0",conv_layer(ni, nh, 1, act_fn=act_fn)),
                   (f"conv_1",conv_layer(nh, nh, 3, stride=stride, act_fn=act_fn)),
                   (f"conv_2",conv_layer(nh, nf, 1, zero_bn=zero_bn, act=False))
        ]
        if sa: layers.append(('sa', SimpleSelfAttention(nf,ks=1,sym=sym)))
        self.convs = nn.Sequential(OrderedDict(layers))
        self.pool = noop if stride==1 else pool
        self.idconv = noop if ni==nf else conv_layer(ni, nf, 1, act=False)
        self.act_fn =act_fn

    def forward(self, x): return self.act_fn(self.convs(x) + self.idconv(self.pool(x)))

# Cell
# Still no name - just New block YET!
class NewResBlock(nn.Module):
    def __init__(self, expansion, ni, nh, stride=1,
                 conv_layer=ConvLayer, act_fn=act_fn,
                 pool=nn.AvgPool2d(2, ceil_mode=True), sa=False,sym=False, zero_bn=True):
        super().__init__()
        nf,ni = nh*expansion,ni*expansion
        self.reduce = noop if stride==1 else pool
        layers  = [(f"conv_0", conv_layer(ni, nh, 3, stride=1, act_fn=act_fn)), # stride 1 !!!
                   (f"conv_1", conv_layer(nh, nf, 3, zero_bn=zero_bn, act=False))
        ] if expansion == 1 else [
                   (f"conv_0",conv_layer(ni, nh, 1, act_fn=act_fn)),
                   (f"conv_1",conv_layer(nh, nh, 3, stride=1, act_fn=act_fn)), # stride 1 !!!
                   (f"conv_2",conv_layer(nh, nf, 1, zero_bn=zero_bn, act=False))
        ]
        if sa: layers.append(('sa', SimpleSelfAttention(nf,ks=1,sym=sym)))
        self.convs = nn.Sequential(OrderedDict(layers))
        self.idconv = noop if ni==nf else conv_layer(ni, nf, 1, act=False)
        self.merge =act_fn

    def forward(self, x):
        o = self.reduce(x)
        return self.merge(self.convs(o) + self.idconv(o))

# Cell
# v8
class Net():
    def __init__(self, expansion=1, layers=[2,2,2,2], c_in=3, c_out=1000, name='Net'):
        super().__init__()
        self.name = name
        self.c_in, self.c_out,self.expansion,self.layers = c_in,c_out,expansion,layers # todo setter for expansion
        self.stem_sizes = [c_in,32,32,64]
        self.stem_pool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.stem_bn_end = False
        self.block = ResBlock
        self.norm = nn.BatchNorm2d
        self.act_fn=nn.ReLU(inplace=True)
        self.pool = nn.AvgPool2d(2, ceil_mode=True)
        self.sa=False
        self.bn_1st = True
        self.zero_bn=True
        self._init_cnn = init_cnn
        self.conv_layer = ConvLayer

    @property
    def block_szs(self):
        return [64//self.expansion,64,128,256,512] +[256]*(len(self.layers)-4)

    @property
    def stem(self):
        return self._make_stem()
    @property
    def head(self):
        return self._make_head()
    @property
    def body(self):
        return self._make_body()

    def _make_stem(self):
        stem = [(f"conv_{i}", self.conv_layer(self.stem_sizes[i], self.stem_sizes[i+1],
                    stride=2 if i==0 else 1,
                    norm=(not self.stem_bn_end) if i==(len(self.stem_sizes)-2) else True,
                    act_fn=self.act_fn, bn_1st=self.bn_1st))
                for i in range(len(self.stem_sizes)-1)]
        stem.append(('stem_pool', self.stem_pool))
        if self.stem_bn_end: stem.append(('norm', self.norm(self.stem_sizes[-1])))
        return nn.Sequential(OrderedDict(stem))

    def _make_head(self):
        head = [('pool', nn.AdaptiveAvgPool2d(1)),
                ('flat', Flatten()),
                ('fc',   nn.Linear(self.block_szs[-1]*self.expansion, self.c_out))]
        return nn.Sequential(OrderedDict(head))

    def _make_body(self):
        blocks = [(f"l_{i}", self._make_layer(self.expansion,
                        self.block_szs[i], self.block_szs[i+1], l,
                        1 if i==0 else 2, self.sa if i==0 else False))
                  for i,l in enumerate(self.layers)]
        return nn.Sequential(OrderedDict(blocks))

    def _make_layer(self,expansion,ni,nf,blocks,stride,sa):
        return nn.Sequential(OrderedDict(
            [(f"bl_{i}", self.block(expansion, ni if i==0 else nf, nf,
                    stride if i==0 else 1, sa=sa if i==blocks-1 else False,
                    conv_layer=self.conv_layer, act_fn=self.act_fn, pool=self.pool,zero_bn=self.zero_bn))
              for i in range(blocks)]))

    def __call__(self):
        model = nn.Sequential(OrderedDict([
            ('stem', self.stem),
            ('body', self.body),
            ('head', self.head)
        ]))
        self._init_cnn(model)
        model.extra_repr = lambda : f"model {self.name}"
        return model
    def __repr__(self):
        return f" constr {self.name}"

# Cell
me = sys.modules[__name__]
for n,e,l in [[ 18 , 1, [2,2,2 ,2] ],
    [ 34 , 1, [3,4,6 ,3] ],
    [ 50 , 4, [3,4,6 ,3] ],
    [ 101, 4, [3,4,23,3] ],
    [ 152, 4, [3,8,36,3] ],]:
    name = f'net{n}'
    setattr(me, name, partial(Net, expansion=e, layers=l, name=name))
xresnet50      = partial(Net, expansion=4, layers=[3, 4,  6, 3], name='xresnet50')