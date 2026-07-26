"""示例电路图 —— schemdraw 源文件。"""

import schemdraw
import schemdraw.elements as elm
from schemdraw import Drawing


def lc_series():
    """LC 串联谐振 —— 水平画法"""
    d = Drawing(show=False)
    d.config(fontsize=14)
    d += elm.SourceV().right().label("$V_s$").length(4)
    d += elm.Inductor().right().label("$L$").length(4)
    d += elm.Capacitor().right().label("$C$").length(4)
    d.push()
    d += elm.Line().down().length(3)
    d += elm.Line().left().length(12)
    d += elm.Line().up().length(3)
    d.pop()
    return d


def rlc_series():
    """RLC 串联 —— 水平画法"""
    d = Drawing(show=False)
    d.config(fontsize=14)
    d += elm.SourceV().right().label("$V_s$").length(4)
    d += elm.Resistor().right().label("$R$").length(4)
    d += elm.Inductor().right().label("$L$").length(4)
    d += elm.Capacitor().right().label("$C$").length(4)
    d.push()
    d += elm.Line().down().length(3)
    d += elm.Line().left().length(16)
    d += elm.Line().up().length(3)
    d.pop()
    return d
