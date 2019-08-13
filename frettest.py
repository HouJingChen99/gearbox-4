import solid
import pathlib

FIDDLE=.001

def fret1(innerdia, outerdia, circcount, height):
    """
    generates 2d cutout pattern where all the cuts lie between the given inner and outer dia
    This pattern is just a number of circles between 3 and 5 
    """
    cdia=(outerdia-innerdia)/2
    rangle=360/circcount
    offset=(innerdia+(outerdia-innerdia)/2)/2
    cuts=solid.union()([solid.rotate(a=rangle*i,v=(0,0,1))(solid.translate((offset,0))(solid.circle(d=cdia, segments=20))) for i in range(circcount)])
    return solid.linear_extrude(height=height, convexity=circcount+1)(cuts)

def test(d1, d2, c,h):
    disc=solid.cylinder(h=h, d=d2+3)
    cuts=fret1(d1, d2, c, h+FIDDLE*2)
    t=solid.difference()(disc, solid.translate((0,0,-FIDDLE))(cuts))
    pf=pathlib.Path('scadout/test.scad')
    with pf.open('w') as pfo:
        pfo.write(solid.scad_render(t))

