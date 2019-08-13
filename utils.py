#! python

import solid, math

FIDGET=.001

def chamfcylinder(h, r=None, d=None, segments=None, outer=False, chamtop=None, chambase=None,cut=False, fidget=.001):
    """
    This is a smarter version of solid.cylinder, but slightly simpler as well. It creates a cylinder with
    optional 45 degree chamfers at each end. It also allows height to be negative, in which case the cylinder
    goes down (so to speak) rather than up.
    
    Since the cylinder is built from a regular polygon, this class also allows for the lines of the polygon to touch 
    the perfect circle at their centres, rather than the vertices. This only makes a significant difference when
    relatively few segments are used.
    
    It only handles true cylinders - ie it only uses r or d, not r1,r2,d1,d2

    h       : height of cylinder - if negative the cylinder goes down rather than up
    r       : if not None, then the radius of the cylinder
    d       : if r is None then this is the diameter of the cylinder
    segments: number of segments (otherwise openscad default used) - must be present if outer is True
    outer   : if True the the radius / diameter is increased so the segments touch the circle rather than the points
    chamtop : if not None then the decrease in radius for the chamfer at the cylinder top (chamfer angle is 45 degrees), can be -ve for increase.
    chambase: if not None then the decrease in radius for the chamfer at the cylinder base (chamfer angle is 45 degrees), can be -ve for increase.
    cut     : if true make the cylinder a smidgen taller and offset it to prevent zero thickness walls
    """
    r=d/2 if r is None else r
    if outer:
        r=r/math.cos(math.pi/segments)
    cutfudge=FIDGET if cut else 0
    res=[]
    mainheight=abs(h)
    absheight=mainheight
    atop=0 if chamtop is None else abs(chamtop)
    abase=0 if chambase is None else abs(chambase)
    if atop + abase > mainheight:
        scale=mainheight/(atop + abase)
        atop *= scale
        abase *= scale
    if not chambase is None:
        tz=h-cutfudge if h<0 else -cutfudge
        cyl=solid.cylinder(r1=r-chambase, r2=r, segments=segments,h=abase+cutfudge+fidget)
        if tz != 0:
            res.append(solid.translate((0, 0, tz))(cyl))
        else:
            res.append(cyl)
        mainheight -= abase
    if not chamtop is None:
        tz=absheight-atop-fidget if h > 0 else -atop-fidget
        cyl=solid.cylinder(r1=r, r2=r-chamtop, segments=segments,h=atop+cutfudge+fidget)
        if tz==0:
            res.append(cyl)
        else:
            res.append(solid.translate((0, 0, tz))(cyl))
        mainheight -= atop
    if mainheight > 0:
        cyl=solid.cylinder(r=r, h=mainheight+cutfudge*2, segments=segments)
        if h > 0 and abase > 0:
            zoff=abase-cutfudge
        elif h < 0 and atop > 0:
            zoff=-mainheight-atop-cutfudge
        elif h < 0:
            zoff=-absheight-cutfudge
        else:
            zoff=-cutfudge
        if zoff==0:
            res.append(cyl)
        else:
            res.append(solid.translate((0,0,zoff))(cyl))
    if len(res)==1:
        return res[0]
    else:
        return solid.union()(list(res))

def f_arc_range(start, stop, sides):
    """
    returns a generator that yields a sequence of angles to get from start to stop for a polygon of
    given number of sides.
    
    The first number is always start. The last number will be <= stop.
    
    angles in radians.
    
    returns angle in radians
    """
    assert stop>=start, "cannot go backwards (clockwise)!"
    rstart=start
    if start==stop:
        rstop=rstart+2*pi
    else:
        rstop=stop
    diff=math.pi/(sides/2)
    step=0
    a=rstart
    while a < rstop:
        yield a
        step+=1
        a=rstart+step*diff

def polycircle(rad=None, dia=None, sides=4, isouter=False, ang_from=0, ang_to=360, offset=None):
    """
    returns a generator that yields a sequence of points on a subset of a circle (defaults to a complete circle).
    
    Constructing an arc or circle using the openscad primitives is pretty messy, so here is a more basic approach.
    
    The polygon can be outside the perfect circle (i.e radius is to segment centre)
    or inside (radius to to vertex). The first and last coordinates are always on the perfect circle at the exact
    relevant angle to ensure the polycircle gives the best approximation of a tangent to the circle from a line perpendicular
    to the circle at that point.
    
    The generator checks each co-ordinate and if it is less than 1/2 the length of a side from the proper end point
    the point is skipped.
    
    rad      : radius, if None, dia must be specified
    dia      : diameter, used of rad is None, in which case must be a number
    sides    : number of sides (that would be used for a complete circle)
    is_outer : if True then the polygon is on the outside of a circle of the given size, otherwise it is inside
    ang_from : the initial point in the circle (degrees anti-clockwise from positive x-axis)
    ang_to   : the final point in the circle / arc (degrees anti-clockwise from positive x-axis)
    offset   : offsets the output by x&y (i.e. places the centre of the circle at
    
    returns a complex number with x as the real part and y as the imaginary part
    """
    assert sides > 2,"At least 3 sides please!"
    r1=dia/2 if rad is None else rad
    assert isinstance(r1, (int, float)), "given size does not make sense"
    rfrom=math.radians(ang_from)
    rto=math.radians(ang_to)
    if isouter: # switch point gen to mid points of angles and yield a correct first point
        rx=r1/math.cos(math.pi/sides)
        r1=rx
    end_point=complex(r1*math.cos(rto),r1*math.sin(rto))
    if offset:
        rtrans=complex(*offset)
        end_point += rtrans
    if isouter: # switch point gen to mid points of angles and yield a correct first point
        a=f_arc_range(rfrom+math.pi/sides, rto, sides)
        npos = complex(r1*math.cos(rfrom),r1*math.sin(rfrom))
        if offset:
            npos+=rtrans
        yield npos
    else:
        a=f_arc_range(rfrom, rto, sides)
    minlen=r1*math.sin(math.pi/sides)*.6
    try:
        while True:
            ang=next(a)
            npos = complex(r1*math.cos(ang),r1*math.sin(ang))
            if offset:
                npos+=rtrans
            if abs(npos-end_point) < minlen:
                raise StopIteration
            else:
                yield npos
    except StopIteration:
        pass
    yield end_point

def polycirclearray(reverse=False, **kwargs):
    ca=list([(n.real, n.imag) for n in polycircle(**kwargs)])
    if reverse:
        return list(reversed(ca))
    else:
        return ca
