
from .core import DesignElement, LayerConfiguration, DesignTerminal
from .. import conformal_mapping as cm
from .. import transmission_line_simulator as tlsim
import gdspy
import numpy as np
from typing import List, Tuple, Mapping, Dict
from . import squid3JJ #TODO make this qubit class suitable for any squid types
from . import JJ4q
from copy import deepcopy


class PP_Squid(DesignElement):
    """
    PP-Transmon consists of several parts:
    1) Central part - central circuit
    params: center = center of the qubit, w,h,gap = width,height,gap of the Parallel Plate Transmon in the ground cavity
    2) Couplers - claw like couplers for the left and right, rectangular pad couplers on top and bottom
    3) Ground = Ground rectangle around qubit, g_w,g_h,g_t = width,height and thickness of ground frame
    4)layer_configuration
    5)Couplers - coupler classes
    6) jj_params - parameters of the SQUID which here is 3JJ SQUID.#TODO add more information
    """
    def __init__(self, name: str, center: Tuple[float, float],width: float, height: float,gap: float,bridge_gap:float,bridge_w:float, g_w: float, g_h: float,g_t: float,layer_configuration: LayerConfiguration,
                 jj_params: Dict,fluxline_params: Dict,Couplers):
        super().__init__(type='qubit', name=name)
        #qubit parameters
        #self.transformations = transformations# to mirror the structure
        self.center = center
        self.w = width
        self.h = height
        self.gap = gap
        self.g_w = g_w
        self.g_h = g_h
        self.g_t = g_t
        self.b_g = bridge_gap
        self.b_w = bridge_w
        #layers
        self.layer_configuration = layer_configuration

        #couplers
        self.couplers = Couplers

        # JJs and fluxline
        self.JJ_params = jj_params
        self.JJ = None
        self.layers = []
        self.fluxline_params = fluxline_params


    def render(self):
        """
        This function draws everything: qubit,ground,couplers
        """
        qubit_cap_parts=[]
        ground = self.generate_ground()
        # restricted area for a future grid lines
        result_restricted = gdspy.Rectangle((self.center[0]-self.g_w/2,self.center[1]-self.g_h/2),(self.center[0]+self.g_w/2,self.center[1]+self.g_h/2),layer=self.layer_configuration.restricted_area_layer)

        P1 = gdspy.Rectangle((self.center[0]-self.gap/2-self.w,self.center[1]-self.h/2),(self.center[0]-self.gap/2,self.center[1]+self.h/2))
        P2 = gdspy.Rectangle((self.center[0] + self.gap / 2 + self.w, self.center[1] - self.h / 2),(self.center[0] + self.gap / 2, self.center[1] + self.h / 2))


        self.layers.append(9)
        result = gdspy.boolean(ground, P1, 'or', layer=self.layer_configuration.total_layer)
        result = gdspy.boolean(result, P2, 'or', layer=self.layer_configuration.total_layer)

        #change here if case to allow Manhatten-style junctions
        P1_bridge = gdspy.Rectangle((self.center[0]-self.gap/2,self.center[1]+self.h/2),(self.center[0]-self.b_g/2,self.center[1]+self.h/2-self.b_w))
        P2_bridge = gdspy.Rectangle((self.center[0] + self.gap / 2, self.center[1]+self.h/2-2*self.b_w),(self.center[0] + self.b_g / 2, self.center[1]+self.h/2-3*self.b_w))


        qubit_cap_parts.append(gdspy.boolean(P1, P1_bridge, 'or', layer=8))
        qubit_cap_parts.append(gdspy.boolean(P2, P2_bridge, 'or', layer=9))

        result = gdspy.boolean(result, P1_bridge, 'or', layer=self.layer_configuration.total_layer)
        result = gdspy.boolean(result, P2_bridge, 'or', layer=self.layer_configuration.total_layer)
        self.layers.append(self.layer_configuration.total_layer)

        f = self.fluxline_params
        l, t_m, t_r, gap, l_arm, h_arm, s_gap = f['l'],f['t_m'],f['t_r'],f['gap'],f['l_arm'],f['h_arm'],f['s_gap']

        flux = PP_Squid_Fluxline(l, t_m, t_r, gap, l_arm, h_arm, s_gap)

        fluxline = flux.render(self.center, self.w, self.h)['positive']

        #removing ground where the fluxline is
        result = gdspy.boolean(result, gdspy.Rectangle((self.center[0]-l_arm/2-t_r-self.g_t,self.center[1]+self.h/2+0.01),(self.center[0]+3*l_arm/2+t_r+t_m+self.g_t,self.center[1]+self.h/2+250)), 'not', layer=self.layer_configuration.total_layer)

        result = gdspy.boolean(result, fluxline, 'or', layer=self.layer_configuration.total_layer)

        # add couplers
        last_step_cap = [gdspy.boolean(gdspy.boolean(P2, P2_bridge, 'or'),gdspy.boolean(P1, P1_bridge, 'or'),'or')]
        self.layers.append(self.layer_configuration.total_layer)

        # Box for inverted Polygons
        box = gdspy.Rectangle((self.center[0] - self.g_w / 2, self.center[1] - self.g_h / 2),(self.center[0] + self.g_w / 2, self.center[1] + self.g_h / 2))

        if len(self.couplers) != 0:
            for id, coupler in enumerate(self.couplers):
                coupler_parts = coupler.render(self.center, self.g_w,self.g_h)

                result = gdspy.boolean(coupler_parts['positive'], result, 'or',
                                       layer=self.layer_configuration.total_layer)

                #Extend ground around coupler
                l1   = coupler.l1
                l2   = coupler.l2
                t    = coupler.t
                gap  = coupler.gap
                side = coupler.side
                height_left = coupler.height_left
                height_right = coupler.height_right
                #to make sure ground is placed correctly
                if l1 < t:
                    l1 = t
                if l2 < t:
                    l2 = t

                if side =='right':
                    #upper
                    extended = gdspy.Rectangle((self.center[0]+self.g_w/2-l1-self.g_t+t,self.center[1]+height_right*self.g_h/2),(self.center[0]+self.g_w/2-l1+t,self.center[1]+gap+height_right*self.g_h/2+t+self.g_t+gap))
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]+t+self.g_w/2-l1,self.center[1]+gap+height_right*self.g_h/2+t+gap),(self.center[0]+self.g_w/2+2*gap+t+self.g_t,self.center[1]+gap+height_right*self.g_h/2+t+self.g_t+gap)),'or')
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]+self.g_w/2+2*gap+t,self.center[1]+gap+height_right*self.g_h/2+t+gap),(self.center[0]+self.g_w/2+2*gap+t+self.g_t,self.center[1]+5+gap)), 'or')
                    #lower
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]+t+self.g_w/2-l2-self.g_t,self.center[1]-height_right*self.g_h/2),(self.center[0]+t+self.g_w/2-l2,self.center[1]-gap-height_right*self.g_h/2-t-self.g_t-gap)), 'or')
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]+t+self.g_w/2-l2,self.center[1]-gap-height_right*self.g_h/2-t-gap),(self.center[0]+self.g_w/2+2*gap+t+self.g_t,self.center[1]-gap-height_right*self.g_h/2-t-self.g_t-gap)),'or')
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]+self.g_w/2+2*gap+t,self.center[1]-gap-height_right*self.g_h/2-t-gap),(self.center[0]+self.g_w/2+2*gap+t+self.g_t,self.center[1]-5-gap)), 'or')
                    result = gdspy.boolean(result,extended,'or')
                    # box for inverted polygon
                    box = gdspy.boolean(box, gdspy.Rectangle((self.center[0] + self.g_w / 2 + self.g_t + 2 * gap + t,
                                                              self.center[
                                                                  1] - height_right * self.g_h / 2 - self.g_t - 2 * gap - t),
                                                             (self.center[0] + self.g_w / 2 - l1 + t, self.center[
                                                                 1] + height_right * self.g_h / 2 + self.g_t + 2 * gap + t)),
                                        'or', layer=self.layer_configuration.inverted)

                if side =='left':
                    #upper
                    extended = gdspy.Rectangle((self.center[0]-self.g_w/2+l1+self.g_t-t,self.center[1]+height_left*self.g_h/2),(self.center[0]-t-self.g_w/2+l1,self.center[1]+gap+height_left*self.g_h/2+t+self.g_t+gap))
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]-t-self.g_w/2+l1,self.center[1]+gap+height_left*self.g_h/2+t+gap),(self.center[0]-self.g_w/2-2*gap-t-self.g_t,self.center[1]+gap+height_left*self.g_h/2+t+self.g_t+gap)),'or')
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]-self.g_w/2-2*gap-t,self.center[1]+gap+height_left*self.g_h/2+t+gap),(self.center[0]-self.g_w/2-2*gap-t-self.g_t,self.center[1]+5+gap)), 'or')
                    #lower
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]-t-self.g_w/2+l2+self.g_t,self.center[1]-height_left*self.g_h/2),(self.center[0]-t-self.g_w/2+l2,self.center[1]-gap-height_left*self.g_h/2-t-self.g_t-gap)), 'or')
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]-t-self.g_w/2+l2,self.center[1]-gap-height_left*self.g_h/2-t-gap),(self.center[0]-self.g_w/2-2*gap-t-self.g_t,self.center[1]-gap-height_left*self.g_h/2-t-self.g_t-gap)),'or')
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]-self.g_w/2-2*gap-t,self.center[1]-gap-height_left*self.g_h/2-t-gap),(self.center[0]-self.g_w/2-2*gap-t-self.g_t,self.center[1]-5-gap)), 'or')
                    result = gdspy.boolean(result,extended,'or')

                    #box for inverted polygon
                    box = gdspy.boolean(box, gdspy.Rectangle((self.center[0] - self.g_w / 2 - self.g_t - 2 * gap - t,self.center[1] - height_left * self.g_h / 2 - self.g_t - 2 * gap - t),(self.center[0] - self.g_w / 2 + l1 - t, self.center[1] + height_left * self.g_h / 2 + self.g_t + 2 * gap + t)),'or', layer=self.layer_configuration.inverted)

                if side == 'top':
                    extended = gdspy.Rectangle((self.center[0]-self.g_w/2+l1-gap-self.g_t,self.center[1]+self.g_h/2),(self.center[0]-self.g_w/2+l1-gap,self.center[1]+self.g_h/2+t+gap+gap))
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]-self.g_w/2+l1-gap-self.g_t,self.center[1]+self.g_h/2+t+gap+gap),(self.center[0]-self.g_w/2+l1-gap+l2/2-5,self.center[1]+self.g_h/2+t+gap+gap+self.g_t)),'or')
                    extended = gdspy.boolean(extended, gdspy.Rectangle((self.center[0]-self.g_w/2+l1+l2+gap,self.center[1]+self.g_h/2),(self.center[0]-self.g_w/2+l1+l2+self.g_t+gap,self.center[1]+self.g_h/2+t+gap+gap)), 'or')
                    extended = gdspy.boolean(extended, gdspy.Rectangle((self.center[0]-self.g_w/2+l1+l2+self.g_t+gap,self.center[1] + self.g_h / 2 + t + gap + gap),(self.center[0]-self.g_w/2+l1+l2/2+gap+5,self.center[1] + self.g_h / 2 + t + gap + gap + self.g_t)),'or')
                    result = gdspy.boolean(result,extended,'or')

                    # box for inverted polygon
                    box = gdspy.boolean(box,gdspy.Rectangle((self.center[0]-self.g_w/2+l1-gap-self.g_t,self.center[1]+self.g_h/2),(self.center[0]-self.g_w/2+l1+l2+self.g_t+gap,self.center[1] + self.g_h / 2 + t + gap + gap + self.g_t)),'or', layer=self.layer_configuration.inverted)


                if side == 'bottom':
                    extended = gdspy.Rectangle((self.center[0]-self.g_w/2+l1-gap-self.g_t,self.center[1]-self.g_h/2),(self.center[0]-self.g_w/2+l1-gap,self.center[1]-self.g_h/2-t-gap-gap))
                    extended = gdspy.boolean(extended,gdspy.Rectangle((self.center[0]-self.g_w/2+l1-gap-self.g_t,self.center[1]-self.g_h/2-t-gap-gap),(self.center[0]-self.g_w/2+l1-gap+l2/2-5,self.center[1]-self.g_h/2-t-gap-gap-self.g_t)),'or')
                    extended = gdspy.boolean(extended, gdspy.Rectangle((self.center[0]-self.g_w/2+l1+l2+gap,self.center[1]-self.g_h/2),(self.center[0]-self.g_w/2+l1+l2+self.g_t+gap,self.center[1]-self.g_h/2-t-gap-gap)), 'or')
                    extended = gdspy.boolean(extended, gdspy.Rectangle((self.center[0]-self.g_w/2+l1+l2+self.g_t+gap,self.center[1] - self.g_h / 2 - t - gap-gap),(self.center[0]-self.g_w/2+l1+l2/2+gap+5,self.center[1] - self.g_h / 2 - t - gap-gap- self.g_t)),'or')
                    result = gdspy.boolean(result,extended,'or')

                    # box for inverted polygon
                    box = gdspy.boolean(box, gdspy.Rectangle(
                        (self.center[0] - self.g_w / 2 + l1 - gap - self.g_t, self.center[1] - self.g_h / 2), (self.center[0] - self.g_w / 2 + l1 + l2 + self.g_t + gap,self.center[1] - self.g_h / 2 - t - gap - gap - self.g_t)), 'or',layer=self.layer_configuration.inverted)

                if coupler.coupler_type == 'coupler':
                        qubit_cap_parts.append(gdspy.boolean(coupler.result_coupler, coupler.result_coupler, 'or',layer=10+id))
                        self.layers.append(10+id)
                        last_step_cap.append(coupler.result_coupler)
        qubit_cap_parts.append(gdspy.boolean(result,last_step_cap,'not'))
        print(qubit_cap_parts)

        inverted = gdspy.boolean(box, result, 'not',layer=self.layer_configuration.inverted)

        # add JJs
        if self.JJ_params is not None:
            self.JJ_coordinates = (self.center[0],self.center[1])
            JJ = self.generate_JJ()

        return {'positive': result,
                    'restricted': result_restricted,
                    'qubit': result,
                    'qubit_cap': qubit_cap_parts,
                    'JJ': JJ,
                    'inverted': inverted
                    }

    def generate_ground(self):
        x = self.g_w
        y = self.g_h
        z = self.center
        t = self.g_t
        ground1 = gdspy.Rectangle((z[0] - x / 2, z[1] - y / 2), (z[0] + x / 2, z[1] + y / 2))
        ground2 = gdspy.Rectangle((z[0] - x / 2 + t, z[1] - y / 2 + t), (z[0] + x / 2 - t, z[1] + y / 2 - t))
        ground = gdspy.fast_boolean(ground1, ground2, 'not')
        return ground

    def rotate_point(point, angle, origin):
        """
        Rotate a point counterclockwise by a given angle around a given origin.

        The angle should be given in radians.
        """
        ox, oy = origin
        px, py = point
        qx = ox + np.cos(angle) * (px - ox) - np.sin(angle) * (py - oy)
        qy = oy + np.sin(angle) * (px - ox) + np.cos(angle) * (py - oy)
        return qx, qy

    def generate_JJ(self):
        #cheap Manhatten style
        reach = 32
        result = gdspy.Rectangle((self.center[0]-self.b_g/2,self.center[1]+self.h/2-self.b_w/3+self.JJ_params['a1']/2),(self.center[0]-self.b_g/2+reach,self.center[1]+self.h/2-self.b_w/3-self.JJ_params['a1']/2))

        result = gdspy.boolean(result,gdspy.Rectangle((self.center[0]-self.b_g/2,self.center[1]+self.h/2-2*self.b_w/3+self.JJ_params['a1']/2),(self.center[0]-self.b_g/2+reach,self.center[1]+self.h/2-2*self.b_w/3-self.JJ_params['a1']/2))
,'or')

        result = gdspy.boolean(result,gdspy.Rectangle((self.center[0]+self.b_g/2,self.center[1]+self.h/2-2*self.b_w),(self.center[0]+self.b_g/2+self.JJ_params['a2'],self.center[1]+self.h/2-2*self.b_w+reach)), 'or')
        result = gdspy.boolean(result, result, 'or', layer=self.layer_configuration.jj_layer)

        angle = self.JJ_params['angle_JJ']
        result.rotate(angle, (self.JJ_coordinates[0], self.JJ_coordinates[1]))

        return result


class PP_Squid_Coupler:
    """
    This class represents a coupler for a PP_Squid, note that the top position is reserved for the fluxline.
    There are several parameters:
    1) l1 - length of the upper claw finger
    2) l2 - length of the lower claw finger
    3) t  - thickness of the coupler
    4) gap - gap between ground and coupler
    5) side - which side the coupler is on
    6) heightl / heightr - height as a fraction of total length
    """
    def __init__(self, l1,l2,t,gap,side = 'left',coupler_type = 'none',heightl = 1,heightr=1):
        self.l1 = l1
        self.l2 = l2
        self.t = t
        self.gap = gap
        self.side = side
        self.coupler_type = coupler_type
        self.ground_t = 10 #<-- temporary fix for the gds creation
        self.height_left = heightl
        self.height_right = heightr
    def render(self, center, g_w,g_h):
        result = 0
        if self.side == "left":
            result = gdspy.Rectangle((center[0]-g_w/2-self.t-self.gap,center[1]-self.height_left*g_h/2-self.gap),(center[0]-g_w/2-self.gap,center[1]+self.height_left*g_h/2+self.gap))
            if self.height_left == 1:
                upper  = gdspy.Rectangle((center[0]-g_w/2-self.t-self.gap,center[1]+g_h/2+self.gap),(center[0]-g_w/2+self.l1-self.gap-self.t,center[1]+g_h/2+self.t+self.gap))
                lower  = gdspy.Rectangle((center[0]-g_w/2-self.t-self.gap,center[1]-g_h/2-self.gap-self.t),(center[0]-g_w/2+self.l2-self.gap-self.t,center[1]-g_h/2-self.gap))
            line   = gdspy.Rectangle((center[0]-g_w/2-self.t-self.gap-self.gap-self.ground_t,center[1]-5),(center[0]-g_w/2-self.t-self.gap,center[1]+5))#modified here ;), remove ground_t
            if self.height_left ==1:
                result = gdspy.boolean(result, upper, 'or')
                result = gdspy.boolean(result, lower, 'or')
            result = gdspy.boolean(result, line, 'or')


        if self.side == "right":
            result = gdspy.Rectangle((center[0]+g_w/2+self.t+self.gap,center[1]-self.height_right*g_h/2-self.gap),(center[0]+g_w/2+self.gap,center[1]+self.height_right*g_h/2+self.gap))
            if self.height_right == 1:
                upper  = gdspy.Rectangle((center[0]+g_w/2+self.t+self.gap,center[1]+g_h/2+self.gap),(center[0]+g_w/2-self.l1+self.gap+self.t,center[1]+g_h/2+self.t+self.gap))
                lower  = gdspy.Rectangle((center[0]+g_w/2+self.t+self.gap,center[1]-g_h/2-self.gap-self.t),(center[0]+g_w/2-self.l2+self.gap+self.t,center[1]-g_h/2-self.gap))

            line = gdspy.Rectangle((center[0]+g_w/2+self.t+self.gap+self.gap,center[1]-5),(center[0]+g_w/2+self.t+self.gap,center[1]+5))
            if self.height_right == 1:
                result = gdspy.boolean(result, upper, 'or')
                result = gdspy.boolean(result, lower, 'or')
            result = gdspy.boolean(result, line, 'or')

        if self.side == "top":
            result = gdspy.Rectangle((center[0]-g_w/2+self.l1,center[1]+g_h/2+self.gap),(center[0]-g_w/2+self.l1+self.l2,center[1]+g_h/2+self.gap+self.t))
            line   = gdspy.Rectangle((center[0]-g_w/2+self.l1+self.l2/2-5,center[1]+g_h/2+self.gap+self.t),(center[0]-g_w/2+self.l1+self.l2/2+5,center[1]+g_h/2+self.gap+self.t+self.gap))
            result = gdspy.boolean(result, line, 'or')

        if self.side == "bottom":
            result = gdspy.Rectangle((center[0]-g_w/2+self.l1,center[1]-g_h/2-self.gap),(center[0]-g_w/2+self.l1+self.l2,center[1]-g_h/2-self.gap-self.t))
            line   = gdspy.Rectangle((center[0]-g_w/2+self.l1+self.l2/2-5,center[1]-g_h/2-self.gap-self.t),(center[0]-g_w/2+self.l1+self.l2/2+5,center[1]-g_h/2-self.gap-self.t-self.gap))
            result = gdspy.boolean(result, line, 'or')

        self.result_coupler = result

        return {
            'positive': result
                        }

class PP_Squid_Fluxline:
    """
    This class represents a Flux_line for a PP_Squid. Design inspired from  Vivien Schmitt. Design, fabrication and test of a four superconducting quantum-bit processor. Physics[physics]
    There are several parameters:
    1) l     - total length of the flux line to the Squid
    2) t_m   - main line thickness, standard is 2*t_r
    3) t_r   - return line thickness
    4) gap   - gap between Squid and line
    5) l_arm - length of one sidearm
    6) h_arm - height of the return arm
    7) s_gap - gap between main and return fluxline
    """
    def __init__(self, l,t_m,t_r,gap,l_arm,h_arm,s_gap):
        self.l      = l
        self.t_m    = t_m
        self.t_r    = t_r
        self.gap    = gap
        self.l_arm  = l_arm
        self.h_arm  = h_arm
        self.s_gap  = s_gap

    def render(self, center, width,height):
        start = [center[0]+self.l_arm/2,center[1]+self.t_r+self.l+height/2+self.gap]
        points = [start+[0,0],start+[self.t_m,0],start+[self.t_m,-self.l],start+[self.t_m+self.l_arm,-self.l]]
        points.append(start+[self.t_m+self.s_gap,-self.l+self.h_arm])
        points.append(start+[self.t_m+self.s_gap,0])
        points.append(start + [self.t_m + self.s_gap+self.t_r, 0])
        points.append(start + [self.t_m + self.s_gap + self.t_r, -self.l+self.h_arm])
        points.append(start + [self.t_m + self.l_arm+ self.t_r, -self.l])
        points.append(start + [self.t_m + self.l_arm+ self.t_r, -self.l-self.t_r])
        points.append(start + [- self.l_arm- self.t_r, -self.l-self.t_r])
        points.append(start + [- self.l_arm - self.t_r, -self.l])
        points.append(start + [-self.t_r-self.s_gap, -self.l+self.h_arm])
        points.append(start + [-self.t_r - self.s_gap, 0])
        points.append(start + [- self.s_gap, 0])
        points.append(start + [- self.s_gap, -self.l+self.h_arm])
        points.append(start + [- self.l_arm, -self.l])
        points.append(start + [0, -self.l])
        points = [(i[0]+i[2],i[1]+i[3]) for i in points]
        result = gdspy.Polygon(points)
        return {
            'positive': result
                        }

