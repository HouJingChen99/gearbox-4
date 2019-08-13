import solid
import solid.utils as sutils
import math
import pathlib
from collections import OrderedDict
from utils import chamfcylinder

from frettest import fret1 as fret1

"""
a module that builds on solidpython primarily to provide additional automation for making sets of gears, allowing OpenSCAD to be
used to preview the whole or subsets of an assembly and subsequently generate STL files for further processing.

It uses gearsV5.1 (https://www.thingiverse.com/thing:2912679) ,put the scad file in the same folder as this python module

Using openSCAD in auto-reload mode allows different subsets of the assembly to be quickly generated and previewed.

It is used as a 2 phase process:
   Initially all the various elements of the total assembly are declared in a set of function calls. This builds an in memory
   database of objects that represent the entire assembly

   Thereafter calls can be made to generate an openSCAD file to view any subset of the parts of the resulting object.

Simple use
==========

start a python3 console

import this module:
    import gearbox as gt

display a brief list of all the bits:
    gt.listallparts()

display a more detailed list of gearpairs:
    gt.listpart('axlecomp', '*', expand=1)

generate a scad file with the whole assembly:
    gt.rendx((('plate',(0,1)),('axlecomp',(0,1,2,3,4,5,6)),('extrapart',(1,3,4,5))), True)

    This creates the file scadout/test.scad
    Now run openSCAD and open that file. If you set autoreload you can then use the python console to generate single parts or groups of parts
    and openSCAD will automatically refresh the display to match.

generate a scad file with everything except the to[p plate:
    gt.rendx((('plate',(0,)),('axlecomp',(0,1,2,3,4,5,6)),('extrapart',(1,3,4,5))), True)

generate a scad file with just the gears that drive the second hand:
     gt.rendx((('axlecomp',(0,1,2,)),), True)

If you change the last parameter to False, each part will generate it's own scad file
    scadout/type-part.scad

Within openscad you can then use render and export to get an stl file

Some info on the internals
==========================
The "database" identifies objects by type (a string) and by name within the type (a string).

Objects can be retrieved from the database by calling resolvename().

see clock1 near the end of the file for example usage

To use this for making gear sets:
    
*   Call gearstyle() to declare standard style of gear. Usually only a few of these (typically 1 to 4) are needed, often in pairs.
    A style sets the thickness of the gear, it's offset from a notional baseline and the total thickness occupied by the gear.
    This allows easy setup of pairs where one is thick and the other is thin, aligned to the centre of the thick one.

*   Call plate() to declare any plates that are required. Plates are used to locate axles and pillars. The pillars are used to align
    and locate a pair of plates. When the 3D part is generated it is automatically shaped to encompass all the pillars and axles
    linked to the plate.

*   Call pillarbits to declare the pillars to connect plates. Each pillar has a location (in x/y) and various parameters to define it shape.
    By convention each pillar is part of the base plate and has lugs to locate the top plate. 

*   Call axle to declare each shaft the gears will be mounted on, The axle's are linked to the plates they connect and can arrange for
    sockets for the axle to be added to each plate.

*   Call gearpair to declare each pair of gears, this shows which axles each gear is on and the number of teeth it has, as well as it's 
    height from the base.

*   Call axlepart to declare each printable part. This declares the axle the part relates to. Typically a pair of gears (from 2 gearpairs,
    that each have a gear on the given axle, and spacers to pad out the height to the next axlepart or the top plate. By convention the larger
    is the lower gear so it can be printed without supports.
"""

FIDGET=.001 # overlap added to difference parts to prevent zero thickness planes

PADFIDGET=.01 # most axlegear components have pads to space them to the next component, this fidget factor reduces the pad size v slightly to
              # make sure the components don't get too tight vertically

#parameters to cut holes for various possible shafts. These are **kwargs for calling btsleeve
#The height is determined elsewhere to match the location
shaftparams={
    'bt2mm' : {'btdia':2, 'segments':8, 'outer':True, 'chamfer':.3, 'gripsize': 2, 'increasedia':1.6},
    'bt3mm' : {'btdia':3, 'segments':6, 'outer':True, 'chamfer':.3, 'gripsize': 2, 'increasedia':1.6},
    'bt4mm' : {'btdia':3.9, 'segments':6, 'outer':True, 'chamfer':.3, 'gripsize': 2, 'increasedia':1.6}, # using 4 gives a loose fit
    'bt5mm' : {'btdia':5, 'segments':6, 'outer':True, 'chamfer':.3, 'gripsize': 2, 'increasedia':1.6},
    'bt5mmo': {'btdia':5, 'segments':8, 'outer':True, 'chamfer':.3, 'gripsize': 2, 'increasedia':1.6},
}

def sqr(x):
    return x*x

def cube(x):
    return x*x*x

def fit_spur_gears(teetha, teethb, spacing):
    """
    This is the python equivalent of the function defined at http://www.thingiverse.com/thing:3575
    """
    return (180 * spacing * teetha * teethb  +  180
        * math.sqrt(-(2*teetha*cube(teethb)-(sqr(spacing)-4)*sqr(teetha)*sqr(teethb)+2*cube(teetha)*teethb))) / (
            teetha*sqr(teethb) + sqr(teetha)*teethb)

sutils.use("gears_v5.1.scad")

allnames={} # grand list of everything declared, indexed by class and then object name by the namedObj constructor.

class namedObj():
    """
    generic class for objects with names to make life easier for humans
    """
    def __init__(self, name, parent=None):
        self.name=name
        self.parent=parent
        cname=self.namelist()
        if not cname in allnames:
            allnames[cname]=OrderedDict()
        namelist=allnames[cname][name]=self

    def namelist(self):
        """
        by default every class has it's own list of named instances, but this method can be overridden to allow multiple classes
        to share a single namespace.
        """
        return type(self).__name__

    fstrhead='{indent}{nclass:9s} {label} {a.name:12s}'
    fstrtail=''

    def prettystr(self, indent='', label='', expand=0):
        basestr=(self.fstrhead+self.fstrtail).format(indent=indent, nclass=self.namelist(), label=label, a=self)
        if expand==0:
            return basestr
        else:
            return basestr+'\n'+ '\n'.join([lowerobj.prettystr(indent=indent+'    ', label='%4s' % '[%d]'%ix, expand=expand-1) for ix, lowerobj in enumerate(self.lowerobjlist())])

    def lowerobjlist(self):
        return []

def resolvename(namespace, name, noexcept=False):
    if isinstance(name, namedObj):
        return name
    elif isinstance(name, (str, int)):
        if namespace in allnames:
            ns=allnames[namespace]
            if isinstance(name,str):
                return ns.get(name)
            else:
                return list(ns.values())[name]
        elif noexcept:
            return None
        else:
            raise ValueError("cannot find namepace {}".format(namespace))
    else:
        raise ValueError('name %s of type %s is not a valid namedObj' % (name, type(name).__name__))


class gearstyle(namedObj):
    """
    A small class to define standard gear settings, cos typically there will be far fewer styles than gears.
    
    it defines an offset and height for a gear - typically from the base of a pair of gears

    Typically gears with few teeth will be taller, gears with many teeth will be shorter and aligned to the middle of the corresponding taller gear
    """
    def __init__(self, offset, height, clearance, **kwargs):
        self.offset=offset
        self.height=height
        self.clearance=clearance
        super().__init__(**kwargs)

    def baseoffset(self):
        """
        returns the offset to the base of the gear
        """
        return self.offset

    def topoffs(self):
        """
        returns the top of the gear
        """
        return self.offset+self.height

    fstrtail=' offset {a.offset:7.2f}, height {a.height:7.2f}, clearance {a.clearance:7.2f}'

class locate2D():
    """
    defines a location / vector in x,y.
    
    Primarily used for axles and pillars. Can calculate the angle between vectors to get the 2 gears in a pair
    to mesh correctly in the 3d preview, and the distance between 2 axles, used in calculating the detailed
    model of each gear (pair)
    """
    def __init__(self, locx, locy, **kwargs):
        self.x=locx
        self.y=locy
        super().__init__(**kwargs)

    def distancexy(self, otherloc):
        """
        calculates the distance in the xy plane between this location and another location
        """
        return math.sqrt(sqr(self.x-otherloc.x)+sqr(self.y-otherloc.y))

    def angleToLoc(self, otherloc):
        """
        returns the angle in degrees of the vector from this loc to the other loc.

        anticlockwise, with positive x axis as 0.
        """
        return math.degrees(math.atan2(otherloc.y-self.y, otherloc.x-self.x))

class hourhand(namedObj):
    def __init__(self, shaft, **kwargs):
        self.shaft=shaft
        super().__init__(**kwargs)

    def namelist(self):
        return 'extrapart'

    def generate(self):
        soutl=((1.5, -8), (-1.5, -8), (-1.5, 13), (1.5, 13))
        shape=solid.union()(
            solid.translate((0,-10))(solid.circle(d=6,segments=8)),
            solid.polygon(points=soutl),
            solid.polygon(points=((-3, 12.5), (3, 12.5), (0,16))),
            solid.circle(d=7.5,segments=8),
        )
        hand=solid.linear_extrude(height=1.5, scale=.95)(shape)
        return solid.translate((0,0,21))(solid.difference()(
            hand,
            btsleeve(locx=0, locy=0, base=0,
                top=1.5, **shaftparams[self.shaft]).generate()    
        ))

class minutehand(namedObj):
    def __init__(self, shaft, **kwargs):
        self.shaft=shaft
        super().__init__(**kwargs)

    def namelist(self):
        return 'extrapart'

    def generate(self):
        soutl=((1.35, -9), (-1.35, -9), (-1.35, 14), (1.35, 14))
        shape=solid.union()(
            solid.translate((0,-10))(solid.circle(d=6,segments=8)),
            solid.polygon(points=soutl),
            solid.polygon(points=((-3, 13.5), (3, 13.5), (0,17))),
            solid.circle(d=5.5,segments=8),
        )
        hand=solid.linear_extrude(height=1.5, scale=.95)(shape)
        return solid.translate((0,0,24))(solid.difference()(
            hand,
            btsleeve(locx=0, locy=0, base=0,
                top=1.5, **shaftparams[self.shaft]).generate()    
        ))

class secondhand(namedObj):
    def __init__(self, shaft, **kwargs):
        self.shaft=shaft
        super().__init__(**kwargs)

    def namelist(self):
        return 'extrapart'

    def generate(self):
        soutl=((1.2, -10), (-1.2, -10), (-1.2, 15), (1.2, 15))
        shape=solid.union()(
            solid.translate((0,-11))(solid.circle(d=6,segments=8)),
            solid.polygon(points=soutl),
            solid.polygon(points=((-3, 14.5), (3, 14.5), (0,18))),
            solid.circle(d=4,segments=8),
        )
        hand=solid.linear_extrude(height=1.5, scale=.95)(shape)
        return solid.translate((0,0,27))(solid.difference()(
            hand,
            btsleeve(locx=0, locy=0, base=0,
                top=1.5, **shaftparams[self.shaft]).generate()    
        ))

class smartPart(namedObj):
    """
    a class for generic 3D parts that are built in (typically) 3 phases
    """
    def __init__(self, parttypes=('hull','extra','cuts'), colour=None, **kwargs):
        super().__init__(**kwargs)
        self.allparts={l:{} for l in parttypes}
        self.colour=colour

    def addPart(self, partname, parttype, partgen, **kwargs):
        """
        adds a part to the partlist of the given type
        
        partname:   a useful unique name for the new part within this part for debug and analysis

        parttype:   the type of part - must be a key in self.allparts

        partgen :   a function that will return solid bits to make a part
        
        **kwargs:   all other arguments are passed to the function 'partgen' when the part is generated
            
        """
        assert parttype in self.allparts
        assert callable(partgen)
        self.allparts[parttype][partname]=(partgen, kwargs)

    def _assemble(self, partsetname, assemblyfunc):
        partset=self.allparts[partsetname]
        assembly=None
        if len(partset) > 0:
            for pfunc, pparams in partset.values():
                p=self._trassemble(pfunc=pfunc, **pparams)
                if not p is None:
                    if assembly is None:
                        assembly=assemblyfunc()
                    assembly.add(p)
        return assembly

    def _trassemble(self, pfunc, translate=None, **kwargs):
        try:
            a=pfunc(**kwargs)
        except TypeError:
            print('FAIL calling %s with parameters %s' % (pfunc.__name__, kwargs))
            raise
        if a and translate:
            return solid.translate(translate)(a)
        else:
            return a

    def generate(self, forcecolour=None):
        """
        This version of generate is predicated on the default value of parttypes passed to the constructor
        """
        u=self._assemble('hull',solid.hull)
        x=self._assemble('extra',solid.union)
        if x is None:
            x=u
        elif not u is None:
            x.add(u)
        if x is None:
            return x
        else:
            z=self._assemble('cuts',solid.union)
            final = x if z is None else solid.difference()(x,z)
            if forcecolour:
                return solid.color(forcecolour)(final)
            elif self.colour:
                return solid.color(self.colour)(final)
            else:
                return final

class axle(locate2D, namedObj):
    """
    defines an axle, and links to all the parts it links to / carries
    
    An axle is not printed, it:
        
    *   links all the things on the axle as an ordered list so we can
        space things out etc.
    
    *   links to the plates that are used to locate the axle shaft  and constrain the things on the axle
    """
    def __init__(self, plates={}, **kwargs):
        """
        sets up the initial info about the axle and does some initial resolving of related parts.
        
        plates:     the plates this axle interacts with. The plate parameters are described below
        """
        self.compolist=[]
        self.padheight=0
        super().__init__(**kwargs)
        for platename, plateinfo in plates.items():
            plateob=resolvename('plate', platename)
            if 'support' in plateinfo:
                plateob.addSupport('axle '+ self.name, translate=(self.x, self.y, 0), **plateinfo['support'])
            if 'padup' in plateinfo:
                plateob.addExtra('axlepad ' + self.name, partgen=self.generatepadup, **plateinfo['padup'])
            if 'axlecut' in plateinfo:
                plateob.addCut('axlecut ' + self.name, partgen=self.generatePlatecut, base=0, top=plateob.thickness, **plateinfo['axlecut'])

    def addComponent(self, component):
        """
        adds a component to the axle. keep the list in ascending z-order 
        """
        if self.compolist:
            cbase=component.compbase()
            for ix, oldc in enumerate(self.compolist):
                if oldc.compbase() > cbase:
                    self.compolist.insert(ix,component)
                    break
            else:
                self.compolist.append(component)
        else: # list was empty - just stick it in there
            self.compolist.append(component)

    def getcompindex(self,comp):
        """
        this returns the index of a component in the compolist
        """
        try:
            return self.compolist.index(comp)
        except ValueError:
            print(comp.name, 'not found on axle', self.name, ', '.join([c.name for c in self.compolist]))
            raise

    def getcomponentno(self, ix):
        return self.compolist[ix]

    def getpadheight(self, baseup):
        if self.compolist:
            if baseup:
                return self.compolist[0].compbase()
            else:
                return self.compolist[-1].comptop()
        else:
            return None

    fstrtail= ' at {a.x:7.2f} /{a.y:7.2f}'

    def lowerobjlist(self):
        return self.compolist

    def generatepadup(self, height=None, padtocomp=None, **kwargs):
        if height:
            pheight=height
        elif padtocomp:
            pheight=self.getpadheight(baseup=True)
            if not pheight is None:
                pheight -= padtocomp
        else:
            return None
        self.padheight=pheight
        padcyl = chamfcylinder(h=pheight, segments=24, **kwargs)
        return solid.translate((self.x, self.y, 0))(padcyl)

    def generatePlatecut(self, base, top, shaftargs, blanked=None, **kwargs):
        """
        generates an axle cutout 
        """
        if blanked:
            base += blanked
        cut = (btsleeve(
                locx=self.x, locy=self.y, base=base,
                top=top+self.padheight, cut=True, **shaftparams[shaftargs]).generate())
        return cut

class agear():
    """
    This class describes a single gear.
    
    Instances of this class are normally setup from gearpair's initialisation
    """
    def __init__(self, gaxle, teeth, style, circpitch, secondary, gangle, baseoffset):
        """
        gaxle       : the axle instance the gear is on - can be the name or the axle instance
        teeth       : number of teeth on this gear
        style       : the style of this gear - can be the name or a gearstyle instance
        circpitch   : the circular_pitch parameter required for a gears gear
        secondary   : True if this is the secondary gear
        gangle      : the direction to the other gear - allows them to be drawn with the teeth aligned correctly
        baseoffset  : the z value of the gear's base position - any style offset is added to this
        """
        self.axle=resolvename('axle', gaxle)
        assert isinstance(self.axle, axle)
        self.teeth=teeth
        self.style=resolvename('gearstyle', style)
        assert isinstance(self.style, gearstyle)
        self.cpitch=circpitch
        self.gangle=gangle
        self.seco=secondary
        self.baseoffset=baseoffset

    def outerRadius(self):
        """
        calculates the radius of a circle at the outer edge of the teeth
        """
        return self.teeth*self.cpitch/360 + self.cpitch/180

    def innerRadius(self):
        """
        calculates the radius of a circle at the inner edge of the teeth
        """
        return (self.teeth * self.cpitch / 360 - self.cpitch / 180 - self.style.clearance)-.6
                # make it slightly smaller since circles are regular polygons

    def geartop(self):
        """
        returns the z-value of the top of this gear
        """
        return self.baseoffset + self.style.offset + self.style.height
        
    def gearbase(self):
        """
        returns the z-value of the base of this gear
        """
        return self.baseoffset + self.style.offset

    def generate(self, inplace=True, colour=None):
        """
        generates the gear, ready for scad_render...
        
        sec     : if it is the secondary gear, rotate it 1/2 of tooth angle so teeth mesh
        
        inplace : if True, translate to the axle's location in x/y
        """
        gthick=self.style.height
        g = gear (
            number_of_teeth=self.teeth,
            circular_pitch=self.cpitch,
            pressure_angle=28,
            clearance = self.style.clearance,
            gear_thickness=gthick,
            rim_thickness=gthick,
            rim_width=2,
            hub_thickness=gthick,
            hub_diameter=8,
            bore_diameter=0,
            circles=0,
            backlash=0,
            twist=0,
            involute_facets=0,
            flat=False)
        gearalign=self.gangle+(180 + 180/self.teeth if self.seco else 0) 
        ag = solid.rotate([0,0,gearalign])(g)
        tr=(self.axle.x if inplace else 0,
            self.axle.y if inplace else 0,
            self.style.offset +self.baseoffset)
        return solid.translate(tr)(ag)

class gearpair(namedObj):
    """
    Defines a pair of meshing gears, a primary and a secondary. The primary is
    expected to be the one nearest the input drive (motor or whatever)
    """
    def __init__(self, prim_axle, seco_axle, primteeth, secoteeth, baseoffset, colour=(.7, .7, .7), **kwargs):
        """
        Sets up a pair of meshing gears...
        
        prim_axle   : the axle the primary gear is on
        
        seco_axle   : the axle the secondary gear is on
        
        primteeth   : the number of teeth on the primary gear
        
        secoteeth   : the number of teeth on the secondary gear
        
        baseoffset  : the zoffset of the base of the gear pair
        
        colour      : the colour used to preview the gears of the gearpair (unless overridden) (r,g,b,a in ramge 0..1)
     
        """
        super().__init__(**kwargs)
        paxle=resolvename('axle', prim_axle)
        saxle=resolvename('axle', seco_axle)
        assert isinstance(paxle,axle), 'primary axle seems to be a %s' % type(paxle).__name__
        assert isinstance(saxle,axle)
        axdist=paxle.distancexy(saxle)
        circpitch=fit_spur_gears(primteeth, secoteeth, axdist)
        geardir=paxle.angleToLoc(saxle)
        self.baseoffset=baseoffset
        self.colour=colour
        self.primgear=agear(gaxle=paxle, teeth=primteeth, style='small' if primteeth <=secoteeth else 'large',
                 circpitch=circpitch, secondary=False, gangle=geardir, baseoffset=baseoffset)
        self.secogear=agear(gaxle=saxle, teeth=secoteeth, style='large' if primteeth <= secoteeth else 'small',
                 circpitch=circpitch, secondary=True, gangle=geardir, baseoffset=baseoffset)

    fstrtail=' primary {a.primgear.teeth:02d} teeth on axle {a.primgear.axle.name:8s} secondary {a.secogear.teeth:02d} on axle {a.secogear.axle.name:8s}'

    def getgear(self, primary):
        return self.primgear if primary else self.secogear


    def axlegearisprim(self, axle):
        if self.primgear.axle==axle:
            return True
        elif self.secogear.axle==axle:
            return False
        else:
            raise ValueError('gearpair %s has no gear on axle %s' % (self.name, axle.name))

    def generate(self, gears, colour=None):
        usecolour=self.colour if colour is None else colour
        if gears=='both':
            return solid.color(usecolour)(solid.union()(
                self.primgear.generate(),
                self.secogear.generate()
            ))
        elif gears=='prim':
            return solid.color(usecolour)(self.primgear.generate())
        elif gears=='seco':
            return solid.color(usecolour)(self.secogear.generate())
        else:
            raise ValueError('invalid gears parameter (%s) in gearpair.generate for gearpair %s' % (gears, self.name))

class axpart():
    """
    common functions for any part of an axlecomp
    """
    def __init__(self, partix, axcomp):
        self.partix=partix
        self.axlecomp=resolvename('axlecomp', axcomp)

    fstrhead='{indent}{nclass:13s} {label}'
    fstrtail=''

    def prettystr(self, indent='', label='', expand=0):
        basestr=(self.fstrhead+self.fstrtail).format(indent=indent, nclass=type(self).__name__, label=label, a=self)
        return basestr

class gearpart(axpart):
    """
    defines a gear from a gearpair which is part of a component
    """
    def __init__(self, gearpr, **kwargs):
        super().__init__(**kwargs)
        self.gearpair=resolvename('gearpair', gearpr)
        isprim=self.gearpair.axlegearisprim(self.axlecomp.axle)
        self.whichgear='primary' if isprim else 'secondary'
        self.gear=self.gearpair.getgear(isprim)

    def parttop(self):
        return self.gear.geartop()

    def partbase(self):
        return self.gear.gearbase()

    def generate(self):
        gpart = self.gear.generate()
        return gpart

    def rimInner(self):
        return self.gear.innerRadius()

    def centreOuter(self):
        return self.gear.outerRadius()

    fstrtail=' from gearpair {a.gearpair.name:8s} {a.whichgear:} with {a.gear.teeth:d} teeth'

class autospacepart(axpart):
    """
    defines a spacer that fills between 2 gears, by default using max viable radii
    """
    def __init__(self, sloped=True, **kwargs):
        self.sloped=sloped
        super().__init__(**kwargs)

    def generate(self):
        grbelow=self.axlecomp.getpart(self.partix-1)
        grbtop=grbelow.parttop()
        grbinner=grbelow.gear.innerRadius()
        grabove=self.axlecomp.getpart(self.partix+1)
        grabase=grabove.partbase()
        graouter=grabove.gear.outerRadius()
        cylpars={'h': grabase-grbtop}
        if self.sloped:
            cylpars['r1']=grbinner
            cylpars['r2']=graouter
        else:
            cylpars['r']= graouter
        return solid.translate((self.axlecomp.axle.x, self.axlecomp.axle.y, grbtop-FIDGET))(
            solid.cylinder(**cylpars)
        )

class gearpaduppart(axpart):
    """
    padding on top of a gear to the next thing above it
    """
    def __init__(self, partspec, clearance=.01, **kwargs):
        self.partspec=partspec
        self.clearance=clearance
        super().__init__(**kwargs)

    def parttop(self):
        if not hasattr(self, 'top'):
            nextaxlecompix=self.axlecomp.axle.getcompindex(self.axlecomp)+1
            nextcomp=self.axlecomp.axle.getcomponentno(nextaxlecompix)
            self.top=nextcomp.compbase()-self.clearance
        return self.top

    def generate(self):
        partbelow=self.axlecomp.getpart(self.partix-1)
        partbtop=partbelow.parttop()
        top=self.parttop()
        return solid.translate((self.axlecomp.axle.x, self.axlecomp.axle.y, partbtop-FIDGET))(
            chamfcylinder( h=top-partbtop-PADFIDGET, **self.partspec)
        )

class padtoPlate(axpart):
    """
    pad a component to the plate above
    """
    def __init__(self, platename, partspec, **kwargs):
        self.toPlate=resolvename('plate', platename)
        self.partspec=partspec
        super().__init__(**kwargs)

    def parttop(self):
        return self.toPlate.zbase

    def generate(self):
        partbelow=self.axlecomp.getpart(self.partix-1)
        print('partbelow is a ', type(partbelow).__name__, 'from', partbelow.partbase(), 'to', partbelow.parttop())
        partbtop=partbelow.parttop()
        top=self.parttop()
        print('pad to plate cylinder at %2.2f, %2.2f, %2.2f, d=%2.2f,h=%2.2f' %(self.axlecomp.axle.x, self.axlecomp.axle.y, partbtop-.001, self.partspec['d'], top-partbtop))
        return solid.translate((self.axlecomp.axle.x, self.axlecomp.axle.y, partbtop-.001))(
            chamfcylinder( h=top-partbtop, **self.partspec)
        )

    def centreOuter(self):
        return self.partspec['d']/2

axcompparts={
    'gear': gearpart,
    'autospacer': autospacepart,
    'padup': gearpaduppart,
    'padplate': padtoPlate,
}

def makeaxpart(parttype, **kwargs):
    if parttype in axcompparts:
        return axcompparts[parttype](**kwargs)
    else:
        raise ValueError('unknown axle component part %s' % parttype)

def makeshaft(shafttype, shaftstyle=None, **kwargs):
    if shafttype=='btsleeve':
        if shaftstyle:
#            print('makeshaft type btsleeve using style', shaftstyle)
            return btsleeve(**shaftparams[shaftstyle], **kwargs)
        else:
#            print('makeshaft type btsleeve using kwargs', kwargs)
            return btsleeve(**kwargs)
    else:
        raise ValueError('unknown shafttype %s' % shafttype)

class btsleeve():
    """
    class to make hole for a brass tube shaft.
    
    The shape is chamfered top and bottom and has a short (2mm) length top and bottom of a diameter that
    should be a firm fit for the given size of brass tube. If the total length is longer than required for the chamfers plus
    2 x 2mm (default) bearing grips, the centre is opened up to a slightly larger diameter to reduce the risk of printing flaws making
    it difficult to insert the brass tube
    """
    def __init__(self, base, top, btdia, locx, locy, chamfer=.5, increasedia=1, gripsize=2, **kwargs):
        self.trans=(locx, locy, base-FIDGET)
        self.height=top-base
        self.btdia=btdia
        self.chamfer=chamfer
        self.adddia=increasedia
        self.gripsize=gripsize
        self.kwargs=kwargs

    def generate(self):
        primary=chamfcylinder(h=self.height+FIDGET*2, d=self.btdia, chambase=-self.chamfer/2, chamtop=-self.chamfer/2, **self.kwargs)
        chamspace=self.height-2*self.gripsize-self.adddia
#        print('btsleeve inner chamfer height is', chamspace, 'from height', self.height) 
        if chamspace > 0:
#            print('  inner offset at', self.gripsize+self.chamfer/2, 'height', chamspace)
            return solid.translate(self.trans)(solid.union()(
                solid.translate((0, 0, self.gripsize+self.chamfer/2))(
                    chamfcylinder(h=chamspace, d=self.btdia+self.chamfer, chambase=self.chamfer/2, chamtop=self.chamfer/2, **self.kwargs)),
                primary))
        else:
            return solid.translate(self.trans)(primary)

class axlecomp(namedObj):
    """
    a single printable part, typically 2 gears (from separate pairs) on an axle with added spacers if appropriate.
    
    It can also have a shaft hole through if required
    """
    def __init__(self, caxle, partlist, shaft=None, finalcuts=None, colour='pink', **kwargs):
        """
        defines an axle based component that is added to the part set for later generation. 
                  
        caxle:      the name of the axle or the axle object of which this component is a part.

        partlist:   a list of (most of the) parts that make up the component - an ordered list of the bits (bottom to top)
                    for the component. Order is important as it is used to automatically add spacers and find the top and bottom.
            
        finalcuts:  bits to be removed from the piece after the parts in partlist are combined - typically for an axle shaft.
        
        colour:     the colour used for the preview.
            
        name:       human name for the part
        """
        super().__init__(**kwargs)
        self.axle=resolvename('axle',caxle)
        self.parts = [makeaxpart(partix=partno, axcomp=self, **partdef) for partno, partdef in enumerate(partlist)]
        if shaft is None or len(self.parts)==0:
            self.shaft=None
        else:
            self.shaftparams=shaft
        self.axle.addComponent(self)
        self.colour=colour
        self.finalcuts=finalcuts

    def getpart(self, partix):
        assert partix >=0 and partix < len(self.parts)
        return self.parts[partix]

    def compbase(self):
        """
        returns the z-offset of the base of the component
        """
        return self.parts[0].partbase()

    def comptop(self):
        """
        returns the z-offset of the top of the component
        """
        return self.parts[-1].parttop()

    def generate(self):
        u=solid.union()
        for p in self.parts:
            gg=p.generate()
            if not gg is None:
                u.add(gg)
        
        if not hasattr(self, 'cutout'):
            if self.finalcuts is None or len(self.finalcuts) == 0:
                c=None
            else:
                c=solid.union()
                for cp in self.finalcuts:
                    if 'shafttype' in cp:
                        if 'baseoffset' in cp:
                            ncp=cp.copy()
                            baseoff=ncp.pop('baseoffset')
                        else:
                            ncp=cp
                            baseoff=0
                        s=makeshaft(base=self.parts[0].partbase()+baseoff, top=self.parts[-1].parttop(), locx=self.axle.x, locy=self.axle.y, **ncp).generate()
                    elif 'fretfunc' in cp:
                        lowerpart=self.parts[cp['fretouterpart']]
                        upperpart=self.parts[cp['fretinnerpart']]
                        base=lowerpart.partbase()-FIDGET
                        height=upperpart.parttop()+2*FIDGET-base
                        fpars={
                            'outerdia': lowerpart.rimInner()*2-.3,
                            'innerdia': upperpart.centreOuter()*2,
                            'height': height,}
                        s=solid.translate((self.axle.x, self.axle.y, base))(cp['fretfunc'](**fpars, **cp['fretparams']))
                    else:
                        s=allnames[cp['partgroup']][cp['partname']].generate()
                    if not s is None:
                        c.add(s)
            self.cutout=c
        if self.cutout is None:
            return solid.color(self.colour)(u)
        else:
            return solid.color(self.colour)(solid.difference()(u, self.cutout))

    def compocomps(self):
        for ix, p in enumerate(self.parts):
            yield ix,p

    def prettystr(self, **kwargs):
        self.cbase=self.compbase()
        self.ctop=self.comptop()
        return super().prettystr(**kwargs)

    fstrtail= ' from {a.cbase:3.2f} to {a.ctop:3.2f}'

    def lowerobjlist(self):
        return self.parts

class axlesupport():
    def __init__(self, plate, axle, dia, chamfer=0, padup=None, paddown=None, shaftcut=None):
        """
        sets up an axle support on a plate.
        This comprises:
            a cylinder used as part of the hull used for the plate outline
            any pad used to support the first gear on an axle
            any hole to be made to support an axle shaft
        """
        assert padup is None or paddown is None # at least 1 should be none so the plate has a flat side for printing
        self.dia=dia
        self.chamfer=chamfer
        self.padup=padup
        self.paddown=paddown
        self.shaftcut=shaftcut
        if not shaftcut is None:
            assert 'shafttype' in shaftcut, 'shaftcut dict must have an entry "shafttype" for plate {} with axle {}'.format(plate.name, axle.name)
            assert shaftcut['shafttype'] in shaftparams, 'no entry {} in shaftparams for plate {} with axle{}'.format(
                    shaftcut['shafttype'],plate.name, axle.name)
        self.axle=axle
        self.plate=plate
        self.base=None
        self.top=None

    def axlecut(self):
        """
        generates any axle cutouts required in the plate
        """
        if self.shaftcut is None:
            return None
        else:
#            print('make shaft cutout at {} / {}, base: {}, top: {}, otherparams: {}'.format(self.axle.x, self.axle.y, self.base-FIDGET, self.top+FIDGET, shaftparams[self.shaftcut['shafttype']]))
            base=self.base-FIDGET
            top=self.top+FIDGET
            if 'blanked' in self.shaftcut:
                blanksize=self.shaftcut['blanked']
                if blanksize > 0:
                    base=self.base+blanksize
                else:
                    top=self.top+blanksize
            return btsleeve(
                    locx=self.axle.x, locy=self.axle.y, base=base,
                    top=top, **shaftparams[self.shaftcut['shafttype']]).btsleevegenerate()        

class plate(smartPart):
    """
    A plate that locates the axles and can have links to another plate - typically 1 base plate and one faceplate
    """
    def __init__(self, thickness, zoffset, **kwargs):
        """
        defines a plate which carries axles and spacers and can be specialised with motor mounts etc.
        
        thickness: how thick the plate is. The sign indicates whether the z-offset refers to the underside or topside of the plate
        
        zoffset:   plate's nominal z position, which can be the top or bottom surface. 
        """
        super().__init__(**kwargs)
        if thickness < 0:
            self.zbase=zoffset+thickness
            self.thickness=-thickness
        else:
            self.zbase=zoffset
            self.thickness=thickness

    fstrtail=' base {a.zbase:7.2f}, thickness {a.thickness:7.2f}, colour {a.colour}'

    def addSupport(self, nametail,translate=None, **kwargs):
        """
        parts that need support / connection to a plate call this.
        """
        trz=self.zbase
        if translate is None:
            if trz == 0:
                tr=None
            else:
                tr=(0, 0, trz)
        else:
            tr=(translate[0], translate[1], translate[2]+trz)
        self.addPart(partname='hull for ' + nametail, parttype='hull', 
                    translate=tr, 
                    h=self.thickness, **kwargs)

    def addExtra(self, nametail, translate=None, **kwargs):
        trz=self.zbase+self.thickness
        if translate is None:
            if trz == 0:
                tr=None
            else:
                tr=(0, 0, trz)
        else:
            tr=(translate[0], translate[1], translate[2]+trz)
        self.addPart(partname='extra for ' + nametail, parttype='extra',
                    translate=tr,
                    **kwargs)

    def addCut(self, nametail, translate=None, **kwargs):
        trz=self.zbase
        if translate is None:
            if trz == 0:
                tr=None
            else:
                tr=(0, 0, trz)
        else:
            tr=(translate[0], translate[1], translate[2]+trz)
        self.addPart(partname='cut for ' + nametail, parttype='cuts',
                    translate=tr,
                    **kwargs)

    def addpillar(self, plname):
        pass


class motorMount(locate2D, namedObj):
    """
    This class creates the cutouts in a plate for a 28BYJ-48 stepper motor for both
    the shaft and pins through the locating lugs
    """
    motorholes=[{'name': '-axle support', 'pos': (0,0,0)        , 'mountdia': 12,    'holeparams': {'d': 5.2}}, 
                {'name': '-shaftstep'   , 'pos': (0,0,0)        ,                    'holeparams': {'d': 9.5}}, 
                {'name': '-lug1 support', 'pos': (-8, 17.5, 0)  , 'mountdia': 7,     'holeparams': {'d': 4.05, 'segments':12}},
                {'name': '-lug2 support', 'pos': (-8,-17.5, 0)  , 'mountdia': 7,     'holeparams': {'d': 4.05, 'segments':12}}]

    def __init__(self, mangle, aplate, **kwargs):
        """
        defines the motor shaft location and overall motor orientation
        
        name        : name for this object (from namedObj)
        
        locx, locy  : x and y coords of the motor shaft (from locate2D)
        
        mangle      : orientation of the motor - 0 degrees is along x axis with body of motor along x-axis
        """
        super().__init__(**kwargs)
        self.mangle=mangle
        self.aplate=aplate

    def namelist(self):
        return 'extrapart'

    def addToPlate(self):
        """
        adds the required mount locations and cutouts to the given plate
        """
        pl=resolvename('plate',self.aplate)
        self.pheight=pl.thickness
        pl.addSupport(self.name+'-supports', partgen=self.gensupports)
        pl.addCut(self.name+'-cuts', partgen=self.gencuts)

    def gensupports(self,h):
        u=solid.union()
        for mh in self.motorholes:
            if 'mountdia' in mh:
                u.add(solid.translate(mh['pos'])(solid.cylinder(d=mh['mountdia'], h=h)))
        return solid.translate((self.x, self.y, 0))(solid.rotate((0,0,self.mangle))(u))

    def gencuts(self):
        u=solid.union()
        for mh in self.motorholes:
            u.add(solid.translate((mh['pos'][0], mh['pos'][1], mh['pos'][2]-FIDGET))(solid.cylinder(h=self.pheight+FIDGET*2, **mh['holeparams'])))
        return solid.translate((self.x, self.y, 0))(solid.rotate((0,0,self.mangle))(u))

class motorPegs(namedObj):
    """
    little pegs to lock the motor onto the base plate
    """
    def __init__(self, formotor, **kwargs):
        self.motor=resolvename('extrapart',formotor)
        super().__init__(**kwargs)

    def namelist(self):
        return 'extrapart'

    def generate(self):
        u=solid.union()
        platethick=self.motor.aplate.thickness
        for mh in self.motor.motorholes:
            if '-lug' in mh['name']:
                u.add(solid.translate((mh['pos'][0], mh['pos'][1], -platethick-.15))(solid.union()(
                    solid.translate((0,0,-.5))(chamfcylinder(h=platethick+.5, d=mh['holeparams']['d']-.05, chamtop=.5,segments=24)),
                    solid.translate((0,0,-2.5))(chamfcylinder(h=2.5, d=6.5, chambase=.5, segments=24)))))
        return solid.translate((self.motor.x, self.motor.y, 0))(solid.rotate((0,0,self.motor.mangle))(u))

class motorShaft(locate2D, namedObj):
    """
    adds the motor shaft - can be used to show the shaft or make a cutout for the shaft. The sizes are optimized for cutting out to receive the shaft.
    """
    def __init__(self, onaxle, onplate, lower=True, **kwargs):
        """
        creates the shaft for the motor
        
        onaxle: identifies the axle the motor is located on
        
        onplate: identofies the plate the motor is attached to 
        
        lower:   motor is on lower side of plate (lowest z)
        """
        self.axle=resolvename('axle', onaxle)
        self.plate=resolvename('plate', onplate)
        self.lower=lower
        super().__init__(locx=self.axle.x, locy=self.axle.y, **kwargs)
    
    height      = 9.75
    shoulderheight=3.3
    shaftdia    = 5.0
    acrossflats = 3.05
    flatx       = 6
    flaty       = 1

    def namelist(self):
        return 'extrapart'

    def generate(self):
        shaftbase=self.plate.zbase if self.lower else self.plate.zbase+plate.thickness
        return solid.translate((self.x, self.y, shaftbase))(solid.color('red')(solid.difference() (
            solid.cylinder(d=self.shaftdia, h=self.height, segments=24),     
            solid.union()(
                solid.translate((-self.flatx/2, self.acrossflats/2, self.shoulderheight))(solid.cube((self.flatx, self.flaty, self.height+FIDGET))),
                solid.translate((-self.flatx/2, -self.acrossflats/2-self.flaty, self.shoulderheight))(solid.cube((self.flatx, self.flaty, self.height+FIDGET)))
            )
        )))

STDSUPPORT={'support':{'partgen': chamfcylinder, 'd':7, 'segments':13}}

def generatepillar(x, y, pillarbase, dia, height, poly, pegpoly, pegdia, pegheight):
    pil = solid.translate((x, y, pillarbase))(
            solid.cylinder(d=dia,h=height, segments=poly))
    if pegpoly is None:
        return pil
    else:
        return solid.union()(pil,
            solid.translate((x, y, pillarbase+height))(
                solid.cylinder(d=pegdia, h=pegheight, segments=pegpoly)
            )
        )

def pillarbits(name, locx, locy, d, baseplate=None, basesupport=STDSUPPORT, topplate=None, topsupport=STDSUPPORT, pillarattach=None, pillarsocket=None, pegpoly=4, pegdia=4, **kwargs):
    basep = resolvename('plate', baseplate) if baseplate else None
    topp = resolvename('plate', topplate) if topplate else None
    toppz=topp.zbase
    topthick=topp.thickness
    if basep:
        basepz=basep.zbase+basep.thickness
        basepthick=basep.thickness
        if 'support' in basesupport:
            basep.addSupport('pillar '+ name, translate=(locx, locy, 0), **basesupport['support'])
        if pillarattach==basep.name:
            basep.addExtra('pillar ' + name, partgen=generatepillar, x=locx, y=locy, pillarbase=basepz, dia=d, height=toppz-basepz+.2, poly=6, pegpoly=pegpoly, pegdia=pegdia, pegheight=topthick)            
    if topp:
        if 'support' in topsupport:
            topp.addSupport('pillar '+ name, translate=(locx, locy, 0), **topsupport['support'])
        if pillarsocket==topp.name:
            topp.addCut(nametail='pillarpeg ' + name, translate=(locx, locy, -FIDGET), partgen=solid.cylinder, h=topthick+FIDGET*2,d=pegdia+.1, segments=pegpoly)

def clock1():
    """
    The primary function that declares up all the components of a gearbox for a small clock drive by a single stepper motor
    """
    scaleby=.9          # scaleby allows the overall size / spacing between the axles and pillars to be tweaked without changing anython else.
    gearstyle(name='small', offset=0, height=2.5, clearance=.2)
    gearstyle(name='large', offset=.625, height=1.25, clearance=.2)

    pbase=plate(name="base", thickness=-3, zoffset=0, colour=(.8, .5, .6, 1))
    ptop=plate(name="top", thickness=3, zoffset=16, colour=(.35, .25, .25, 1))
    
    pillarbits(name='p1', locx=47*scaleby, locy=12*scaleby, poly=5, d=6, baseplate='base', topplate='top', pillarattach='base', pillarsocket='top', pegpoly=4, pegdia=4)
    pillarbits(name='p2', locx=12*scaleby, locy=-22*scaleby, poly=5, d=6, baseplate='base', topplate='top', pillarattach='base', pillarsocket='top', pegpoly=4, pegdia=4)
    pillarbits(name='p3', locx=-22*scaleby, locy=12*scaleby, poly=5,d=6, baseplate='base', topplate='top', pillarattach='base', pillarsocket='top', pegpoly=4, pegdia=4)

    ax=axle(name='hands', locx= 0*scaleby,     locy= 0*scaleby, 
            plates={'base':{'support': STDSUPPORT['support'], 'padup': {'padtocomp': .05, 'chamtop':.2, 'd':7}, 'axlecut':{'blanked':1, 'shaftargs': 'bt3mm'}}, 
                    'top': {'support': STDSUPPORT['support'], 'axlecut': {'shaftargs': 'bt5mm'}}})
    
    ax=axle(name='drive', locx=25*scaleby,     locy= 25*scaleby, 
            plates={'base':{'support': STDSUPPORT['support']}, #, 'padup':{'padtocomp': .05, 'chamtop':.2, 'd':7}},
                            'top':{'support': STDSUPPORT['support'], 'axlecut': {'shaftargs': 'bt3mm'}}})

    motorMount(name='stepper', locx= ax.x, locy=ax.y, mangle=45, aplate=pbase).addToPlate()
    
    motorPegs(name='motorlugs', formotor='stepper')

    motorShaft(name='driveshaft', onaxle=ax, onplate='base')

    ax=axle(name='aux1',  locx=25*scaleby,   locy=0*scaleby,
            plates={'base':{'support': STDSUPPORT['support'], 'padup':{'padtocomp': .05, 'chamtop':.2, 'd':7}, 'axlecut':{'blanked':1, 'shaftargs': 'bt3mm'}}, 
                            'top':{'support': STDSUPPORT['support'], 'axlecut': {'shaftargs': 'bt3mm'}}})

    ax=axle(name='aux2',  locx=0*scaleby,     locy=25*scaleby, 
            plates={'base':{'support': STDSUPPORT['support'], 'padup':{'padtocomp': .05, 'chamtop':.2, 'd':6}, 'axlecut':{'blanked':1, 'shaftargs': 'bt3mm'}},
                            'top':{'support': STDSUPPORT['support'], 'axlecut': {'shaftargs': 'bt3mm'}}})

#    motorAdapt(name='mshaft', onaxle='drive')

    gearpair(name='shdrive1', prim_axle='drive', seco_axle='aux1',  primteeth=30, secoteeth=8, baseoffset=2.8, colour=(.7, .4, .4, 1)) 
    gearpair(name='shdrive2', prim_axle='aux1',  seco_axle='hands', primteeth=32, secoteeth=10, baseoffset=.5, colour=(.6, .35, .4, 1))

    gearpair(name='mhdrive1', prim_axle='drive',  seco_axle='aux2', primteeth=15, secoteeth=30, baseoffset=4.9, colour=(.4, .7, .4, 1))
    gearpair(name='mhdrive2', prim_axle='aux2',  seco_axle='hands', primteeth=12, secoteeth=30, baseoffset=7.2, colour=(.25, .6, .4, 1))

    gearpair(name='hhdrive1', prim_axle='hands',  seco_axle='aux1', primteeth=8, secoteeth=32, baseoffset=9.8, colour=(.33, .4, .7, 1))
    gearpair(name='hhdrive2', prim_axle='aux1',  seco_axle='hands', primteeth=10, secoteeth=30, baseoffset=12.2, colour=(.33, .38, .63, 1))

    # driven by drive1, carries shaft for second hand
    axlecomp(name='drive3', caxle='hands', colour=(.4, .4, .75), partlist=(
            {'parttype': 'gear', 'gearpr':'shdrive2'},
            {'parttype': 'padup', 'partspec': {'d':6, 'segments':24, 'chamtop':.2}},        
        ),
        finalcuts=({'shafttype':'btsleeve', 'shaftstyle':'bt2mm'},))

    # driven by drive2, speedup to drive3, intermediate gear for second hand 
    axlecomp(name='drive1', caxle='aux1', colour=(.27,.27, .6), partlist=(
            {'parttype': 'gear', 'gearpr':'shdrive2'},
            {'parttype': 'autospacer', 'sloped': False},
            {'parttype': 'gear', 'gearpr':'shdrive1'},
            {'parttype': 'padup', 'partspec': {'d':6, 'segments':24, 'chamtop':.2}},
        ),
        finalcuts=({'shafttype':'btsleeve', 'shaftstyle':'bt4mm'},
        {'fretfunc' :fret1, 'fretouterpart': 0, 'fretinnerpart': 2, 'fretparams':{'circcount':1}},
    ))
    
    # driven by motor - speed up to drive1 (on way to second hand), slow down to mdrive2 on way to minute hand
    axlecomp(name='drive2', caxle='drive', colour= (.35,.35, .8), partlist=(
            {'parttype': 'gear', 'gearpr':'shdrive1'},
            {'parttype': 'autospacer'},
            {'parttype': 'gear', 'gearpr':'mhdrive1'},
            {'parttype': 'padplate', 'platename': 'top', 'partspec': {'d':7, 'segments':24, 'chamtop':.25}},
        ),
        finalcuts=(
            {'shafttype':'btsleeve', 'shaftstyle':'bt4mm', 'baseoffset':1.5},
            {'partgroup':'extrapart', 'partname': 'driveshaft'},
            {'fretfunc' :fret1, 'fretouterpart': 0, 'fretinnerpart': 2, 'fretparams':{'circcount':2}}
        ))

    # driven by drive2 - slow down to mdrive3 (on way to minute hand), intermediate gear for minute hand
    axlecomp(name='mdrive2', caxle='aux2', colour=(.35, .65, .35), partlist=(
            {'parttype': 'gear', 'gearpr':'mhdrive1'},
            {'parttype': 'autospacer'},
            {'parttype': 'gear', 'gearpr':'mhdrive2'},
            {'parttype': 'padplate', 'platename': 'top', 'partspec': {'d':7, 'segments':24, 'chamtop':.25}},
        ),
        finalcuts=(
            {'shafttype':'btsleeve', 'shaftstyle':'bt4mm'},
            {'fretfunc' :fret1, 'fretouterpart': 0, 'fretinnerpart': 2, 'fretparams':{'circcount':3}}
        ))

    # driven by mdrive2 - (slow down for minute hand), carries the minute hand and the first stage of the reduction for the hour hand
    axlecomp(name='mdrive3', caxle='hands', colour=(.4, .7, .4), partlist=(
            {'parttype': 'gear', 'gearpr':'mhdrive2'},
            {'parttype': 'autospacer'},
            {'parttype': 'gear', 'gearpr':'hhdrive1'},
            {'parttype': 'padup', 'partspec': {'d':6.5, 'segments':24, 'chamtop':.2}},
         ),
         finalcuts=(
            {'shafttype':'btsleeve', 'shaftstyle':'bt3mm'},
            {'fretfunc' :fret1, 'fretouterpart': 0, 'fretinnerpart': 2, 'fretparams':{'circcount':4}},
        ))

    # driven by mdrive3 - final reduction gear for hour hand
    axlecomp(name='hdrive1', caxle='aux1', colour=(.65, .35, .35), partlist=(
            {'parttype': 'gear', 'gearpr':'hhdrive1'},
            {'parttype': 'autospacer'},
            {'parttype': 'gear', 'gearpr':'hhdrive2'},
            {'parttype': 'padplate', 'platename': 'top', 'partspec': {'d':7, 'segments':24, 'chamtop':.25}},
        ),
        finalcuts=(
            {'shafttype':'btsleeve', 'shaftstyle':'bt4mm'},
            {'fretfunc' :fret1, 'fretouterpart': 0, 'fretinnerpart': 2, 'fretparams':{'circcount':5}},
        ))

    axlecomp(name='hdrive2', caxle='hands', colour=(.8, .5, .6), partlist=(
            {'parttype': 'gear', 'gearpr':'hhdrive2'},
            {'parttype': 'padplate', 'platename': 'top', 'partspec' : {'d':7, 'segments':24, 'chamtop': .25}},
        ),
        finalcuts=(
            {'shafttype':'btsleeve', 'shaftstyle':'bt4mm'},
            {'fretfunc' :fret1, 'fretouterpart': 0, 'fretinnerpart': 1, 'fretparams':{'circcount':4}},
        ))

    secondhand(name='simplesecond', shaft='bt2mm')
    minutehand(name='simpleminute', shaft='bt3mm')
    hourhand(name='simplehour', shaft='bt4mm')

def yieldunit(plist):
    """
    returns a generator for all the items in the given list.
    
    plist: a list of items as follows:

    Each item is a 2-tuple:
        0: is the name of an object type ('geartype', plate', 'axle' etc.
        1: is an int - the index into the list of objects of the given type
            - or -
           a string - the name of of the object of the given type
            - or -
           a list of ints / strings to identify objects of the given type
    """
    for pgroup in plist:
        typelist=allnames[pgroup[0]]
        tlv=list(typelist.values())
        if pgroup[1]=='*':
            for item in tlv:
                yield item
        elif isinstance(pgroup[1], int):
            yield tlv[pgroup[1]]
        elif isinstance(pgroup[1], str):
            yield typelist[pgroup[1]]
        else:
            for unitid in pgroup[1]:
                if isinstance(unitid, int):
                    yield tlv[unitid]
                elif isinstance(unitid,str):
                    yield typelist[unitid]
                else:
                    raise ValueError

def listallparts():
    for typename, typelist in allnames.items():
        print('type {:9s}:'.format(typename))
        for typeix, typeent in enumerate(typelist.keys()):
            print('    {:2d}:  {:11s}'.format(typeix, typeent))

def listpart(ctype, name='*', **kwargs):
    if ctype=='*':
        for c in sorted(allnames.keys()):
            listpart(c, name, **kwargs)
            print('')
    elif name=='*':
        for i in allnames[ctype]:
            listpart(ctype, i, **kwargs)
    else:
        x=resolvename(ctype, name)
        ix=name if isinstance(name, int) else list(allnames[ctype].values()).index(x) 
        label='%4s' % '[%d]'%ix
        print(x.prettystr(label=label, **kwargs))

def rendx(plist, testfile=True):
    """
    renders a set of parts to a single file or to multiple files.
    
    plist:  see yieldunit for details
    
    filen:  if '*' then all parts are rendered as a union to the file 'scadout/test.scad'
            otherwise each part is rendered to a separate file named:
                'scadout/<parttype>-<partname>,scad
    """
    opath=pathlib.Path('scadout')
    opath.mkdir(exist_ok=True)
    if testfile:
        all=solid.union()
    ulist=[u for u in yieldunit(plist)]
    for unit in ulist:
        scadunit=unit.generate()
        if testfile:
            all.add(scadunit)
        else:
            pf=opath /(unit.namelist()+'-'+unit.name+'.scad')
            with pf.open('w') as pfo:
                pfo.write(solid.scad_render(scadunit))
    if testfile:
        pf=opath/'test.scad'
        with pf.open('w') as pfo:
            pfo.write(solid.scad_render(all))

"""
Just for convenience, load the data here.
"""
clock1()
