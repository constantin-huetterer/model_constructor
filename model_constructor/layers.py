# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/01_layers.ipynb (unless otherwise specified).

__all__ = ['ConvLayer', 'act_fn', 'Flatten', 'noop', 'Noop', 'DownsampleBlock', 'BasicBlock', 'Bottleneck',
           'DownsampleLayer', 'XResBlock', 'conv1d', 'SimpleSelfAttention', 'ConvBlockBasic', 'ConvBlockBottle',
           'ResBlock']

# Cell
import torch.nn as nn
import torch
from torch.nn.utils import spectral_norm # weight_norm,
from collections import OrderedDict

# Cell
act_fn = nn.ReLU(inplace=True)

class ConvLayer(nn.Sequential):
    """Basic conv layers block"""
    def __init__(self, ni, nf, ks=3, stride=1,
            act=True,  act_fn=act_fn,
            bn_layer=True, bn_1st=True, zero_bn=False,
            padding=None, bias=False, groups=1, **kwargs):

#         self.act = act
        if padding==None: padding = ks//2
        layers = [('conv', nn.Conv2d(ni, nf, ks, stride=stride, padding=padding, bias=bias, groups=groups))]
        act_bn = [('act_fn', act_fn)] if act else []
        if bn_layer:
            bn = nn.BatchNorm2d(nf)
            nn.init.constant_(bn.weight, 0. if zero_bn else 1.)
            act_bn += [('bn', bn)]
        if bn_1st: act_bn.reverse()
        layers += act_bn
        super().__init__(OrderedDict(layers))

# Cell
class Flatten(nn.Module):
    '''flat x to vector'''
    def __init__(self):
        super().__init__()
    def forward(self, x): return x.view(x.size(0), -1)

# Cell

def noop(x): return x

class Noop(nn.Module): # alternative name Merge
    '''Dummy module for vizualize skip conn'''
    def __init__(self):
        super().__init__()

    def forward(self, x):
        return x

# Cell
def DownsampleBlock(conv_layer, ni, nf, ks, stride, act=False, **kwargs):
    '''Base downsample for res-like blocks'''
    return conv_layer(ni, nf, ks, stride, act, **kwargs)

# Cell
class BasicBlock(nn.Module):
    """Basic block (simplified) as in pytorch resnet"""
    def __init__(self, ni, nf,  expansion=1, stride=1, zero_bn=False,
                conv_layer=ConvLayer, act_fn=act_fn,
                downsample_block=DownsampleBlock, **kwargs):
        super().__init__()
        self.downsample = not ni==nf or stride==2
        self.conv = nn.Sequential(OrderedDict([
            ('conv_0', conv_layer(ni, nf, stride=stride, act_fn=act_fn,  **kwargs)),
            ('conv_1', conv_layer(nf, nf, zero_bn=zero_bn, act=False, act_fn=act_fn, **kwargs))]))
        if self.downsample:
            self.downsample = downsample_block(conv_layer, ni, nf, ks=1, stride=stride, act=False, **kwargs)
        self.merge = Noop()
        self.act_conn = act_fn

    def forward(self, x):
        identity = x
        out = self.conv(x)
        if self.downsample:
            identity = self.downsample(x)
        return self.act_conn(self.merge(out + identity))

# Cell
class Bottleneck(nn.Module):
    '''Bottlneck block for resnet models'''
    def __init__(self, ni, nh, expansion=4, stride=1, zero_bn=False,
                conv_layer=ConvLayer, act_fn=act_fn,
                 downsample_block=DownsampleBlock, **kwargs):
#                  groups=1, base_width=64, dilation=1, norm_layer=None
        super().__init__()
        self.downsample = not ni==nh or stride==2
        ni = ni*expansion
        nf = nh*expansion
        self.conv = nn.Sequential(OrderedDict([
            ('conv_0', conv_layer(ni, nh, ks=1,            act_fn=act_fn, **kwargs)),
            ('conv_1', conv_layer(nh, nh, stride=stride,   act_fn=act_fn, **kwargs)),
            ('conv_2', conv_layer(nh, nf, ks=1, zero_bn=zero_bn, act=False, act_fn=act_fn, **kwargs))]))
        if self.downsample:
            self.downsample = downsample_block(conv_layer, ni, nf, ks=1, stride=stride, act=False, act_fn=act_fn, **kwargs)
        self.merge = Noop()
        self.act_conn = act_fn

    def forward(self, x):
        identity = x
        out = self.conv(x)
        if self.downsample:
            identity = self.downsample(x)
        return self.act_conn(self.merge(out + identity))

# Cell
class DownsampleLayer(nn.Sequential):
    """Downsample layer for Xresnet Resblock"""
    def __init__(self, conv_layer, ni, nf, stride, act,
                 pool=nn.AvgPool2d(2, ceil_mode=True), pool_1st=True,
                 **kwargs):
        layers  = [] if stride==1 else [('pool', pool)]
        layers += [] if ni==nf else [('idconv', conv_layer(ni, nf, 1, act=act, **kwargs))]
        if not pool_1st: layers.reverse()
        super().__init__(OrderedDict(layers))

# Cell
class XResBlock(nn.Module):
    def __init__(self, ni, nh, expansion=1, stride=1, zero_bn=True,
                 conv_layer=ConvLayer, act_fn=act_fn, **kwargs):
        super().__init__()
        nf,ni = nh*expansion,ni*expansion
        layers  = [('conv_0', conv_layer(ni, nh, 3, stride=stride, act_fn=act_fn, **kwargs)),
                   ('conv_1', conv_layer(nh, nf, 3, zero_bn=zero_bn, act=False, act_fn=act_fn, **kwargs))
        ] if expansion == 1 else [
                   ('conv_0', conv_layer(ni, nh, 1, act_fn=act_fn, **kwargs)),
                   ('conv_1', conv_layer(nh, nh, 3, stride=stride, act_fn=act_fn, **kwargs)),
                   ('conv_2', conv_layer(nh, nf, 1, zero_bn=zero_bn, act=False, act_fn=act_fn, **kwargs))
        ]
        self.convs = nn.Sequential(OrderedDict(layers))
        self.identity = DownsampleLayer(conv_layer, ni, nf, stride, act=False, act_fn=act_fn, **kwargs) if ni!=nf or stride==2 else Noop()
        self.merge = Noop() # us it to visualize in repr residual connection
        self.act_fn = act_fn

    def forward(self, x): return self.act_fn(self.merge(self.convs(x) + self.identity(x)))

# Cell
# SA module from mxresnet at fastai. todo - add persons!!!

#Unmodified from https://github.com/fastai/fastai/blob/5c51f9eabf76853a89a9bc5741804d2ed4407e49/fastai/layers.py
def conv1d(ni:int, no:int, ks:int=1, stride:int=1, padding:int=0, bias:bool=False):
    "Create and initialize a `nn.Conv1d` layer with spectral normalization."
    conv = nn.Conv1d(ni, no, ks, stride=stride, padding=padding, bias=bias)
    nn.init.kaiming_normal_(conv.weight)
    if bias: conv.bias.data.zero_()
    return spectral_norm(conv)


# Adapted from SelfAttention layer at https://github.com/fastai/fastai/blob/5c51f9eabf76853a89a9bc5741804d2ed4407e49/fastai/layers.py
# Inspired by https://arxiv.org/pdf/1805.08318.pdf
class SimpleSelfAttention(nn.Module):
    def __init__(self, n_in:int, ks=1, sym=False):#, n_out:int):
        super().__init__()
        self.conv = conv1d(n_in, n_in, ks, padding=ks//2, bias=False)
        self.gamma = nn.Parameter(torch.tensor([0.]))
        self.sym = sym
        self.n_in = n_in
    def forward(self,x):
        if self.sym:
            # symmetry hack by https://github.com/mgrankin
            c = self.conv.weight.view(self.n_in,self.n_in)
            c = (c + c.t())/2
            self.conv.weight = c.view(self.n_in,self.n_in,1)
        size = x.size()
        x = x.view(*size[:2],-1)   # (C,N)
        # changed the order of mutiplication to avoid O(N^2) complexity
        # (x*xT)*(W*x) instead of (x*(xT*(W*x)))
        convx = self.conv(x)   # (C,C) * (C,N) = (C,N)   => O(NC^2)
        xxT = torch.bmm(x,x.permute(0,2,1).contiguous())   # (C,N) * (N,C) = (C,C)   => O(NC^2)
        o = torch.bmm(xxT, convx)   # (C,C) * (C,N) = (C,N)   => O(NC^2)
        o = self.gamma * o + x
        return o.view(*size).contiguous()

# Cell
class ConvBlockBasic(nn.Sequential):
    '''Block of conv layers for basic resblock'''
    def __init__(self, conv_layer,ni,nh,nf,stride,zero_bn,act=False,**kwargs):
        super().__init__(OrderedDict([
            ('conv_0', conv_layer(ni, nh, 3, stride=stride, **kwargs)),
            ('conv_1', conv_layer(nh, nf, 3, zero_bn=zero_bn, act=act, **kwargs))
                                ]))

class ConvBlockBottle(nn.Sequential):
    '''Basic block of conv layers for resblock'''
    def __init__(self, conv_layer,ni,nh,nf,stride,zero_bn,act=False,**kwargs):
        super().__init__(OrderedDict([
            ('conv_0', conv_layer(ni, nh, 1,                        **kwargs)),
            ('conv_1', conv_layer(nh, nh, 3, stride=stride,         **kwargs)),
            ('conv_2', conv_layer(nh, nf, 1, zero_bn=zero_bn, act=act, **kwargs))
                                ]))

# Cell
class ResBlock(nn.Module):
    def __init__(self, ni, nh, expansion=1, stride=1, conv_layer=ConvLayer,
                 conv_block=ConvBlockBasic, downsample=DownsampleLayer,
                 act_fn=act_fn, act_id=False, zero_bn=True, sa=False, sym=False, **kwargs):
        super().__init__()
        nf,ni = nh*expansion,ni*expansion
        self.convs = conv_block(conv_layer,ni,nh,nf,stride,zero_bn,act=act_id,act_fn=act_fn,**kwargs)
        self.sa = SimpleSelfAttention(nf,ks=1,sym=sym) if sa else noop
        self.identity = downsample(conv_layer,ni,nf,stride,act=act_id,act_fn=act_fn,**kwargs) if ni!=nf or stride==2 else Noop()
        self.merge =  act_fn if not act_id else Noop()
    def forward(self, x): return self.merge(self.sa(self.convs(x)) + self.identity(x))