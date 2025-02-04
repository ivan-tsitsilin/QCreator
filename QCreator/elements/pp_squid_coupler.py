from .core import DesignElement, LayerConfiguration, DesignTerminal
from .. import conformal_mapping as cm
from .. import transmission_line_simulator as tlsim
import gdspy
import numpy as np
from typing import List, Tuple, Mapping, Dict
from . import squid3JJ #TODO make this qubit class suitable for any squid types
from . import JJ4q
from copy import deepcopy


class PP_Squid_C(DesignElement):
    """
    PP-Transmon consists of several parts:
    1) Central part - central circuit
    params: center = center of the qubit, w,h,gap = width,height,gap of the Parallel Plate Transmon in the ground cavity
    2) Couplers - claw like couplers for the left and right, rectangular pad couplers on top and bottom
    3) Ground = Ground rectangle around qubit, g_w,g_h,g_t = width,height and thickness of ground frame
    4)layer_configuration
    5)Couplers - coupler classes
    6) jj_params - parameters of the SQUID which here is 3JJ SQUID.#TODO add more information
    7) remove_ground - removes the ground on the specified site (left,right, top, bottom)
    8) arms - the parameters for the squid arms for coupling left and right qubits
    """
    def __init__(self, name: str, center: Tuple[float, float],width: float, height: float,gap: float,bridge_gap:float,bridge_w:float, ground_w: float, ground_h: float,ground_t: float,layer_configuration: LayerConfiguration,
                 jj_params: Dict,fluxline_params: Dict,Couplers,transformations:Dict,arms:Dict,remove_ground = {},secret_shift = 0,calculate_capacitance = False):
        super().__init__(type='qubit', name=name)
        #qubit parameters
        self.transformations = transformations# to mirror the structure
        self.center = center
        self.w = width
        self.h = height
        self.gap = gap
        self.g_w = ground_w
        self.g_h = ground_h
        self.g_t = ground_t
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

        self.tls_cache = []
        self.L = 15e-9  # 20nHr
        self.C = {   'coupler0': None,
            'coupler1': None,
             'coupler2': None,
             'coupler3': None,
             'coupler4': None,
            'qubit': None}

        #terminals
        self.terminals = {  # 'coupler0': None,
            # 'coupler1': None,
            # 'coupler2': None,
            # 'coupler3': None,
            # 'coupler4': None,
            # 'flux line': None,
            'qubit': None}


        # remove ground on these sites
        self.remove_ground = remove_ground

        #small coupling pads
        self.arms = arms

        self.secret_shift = secret_shift

        self.calculate_capacitance = calculate_capacitance

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

        #coupler arms left and right
        left_arm    = gdspy.Rectangle((self.center[0]-self.gap/2-self.w,self.center[1]-self.arms['l.w']/2),(self.center[0]-self.g_w/2+self.g_t+self.arms['l.g'],self.center[1]+self.arms['l.w']/2))
        left_arm    = gdspy.boolean(gdspy.Rectangle((self.center[0]-self.g_w/2+self.g_t+self.arms['l.g'],self.center[1]-self.arms['l.ph']/2),(self.center[0]-self.g_w/2+self.g_t+self.arms['l.g']+self.arms['l.pw'],self.center[1]+self.arms['l.ph']/2)), left_arm, 'or')
        P1          = gdspy.boolean(P1, left_arm, 'or')

        right_arm = gdspy.Rectangle((self.center[0] + self.gap / 2 + self.w, self.center[1] + self.arms['r.w'] / 2), (
        self.center[0] + self.g_w / 2 - self.g_t - self.arms['r.g'], self.center[1] - self.arms['r.w'] / 2))
        right_arm = gdspy.boolean(gdspy.Rectangle(
            (self.center[0] + self.g_w / 2 - self.g_t - self.arms['r.g'], self.center[1] + self.arms['r.ph'] / 2), (
            self.center[0] + self.g_w / 2 - self.g_t - self.arms['r.g'] - self.arms['r.pw'],
            self.center[1] - self.arms['r.ph'] / 2)), right_arm, 'or')

        P2 = gdspy.boolean(P2, right_arm, 'or')


        self.layers.append(9)
        result = gdspy.boolean(ground, P1, 'or', layer=self.layer_configuration.total_layer)
        result = gdspy.boolean(result, P2, 'or', layer=self.layer_configuration.total_layer)

        P1_bridge = gdspy.Rectangle((self.center[0]-self.gap/2,self.center[1]+self.h/2),(self.center[0]-self.b_g/2,self.center[1]+self.h/2-self.b_w))
        P2_bridge = gdspy.Rectangle((self.center[0] + self.gap / 2, self.center[1]+self.h/2-2*self.b_w),(self.center[0] + self.b_g / 2, self.center[1]+self.h/2-3*self.b_w))


        qubit_cap_parts.append(gdspy.boolean(P1, P1_bridge, 'or', layer=8+self.secret_shift))
        qubit_cap_parts.append(gdspy.boolean(P2, P2_bridge, 'or', layer=9+self.secret_shift))

        result = gdspy.boolean(result, P1_bridge, 'or', layer=self.layer_configuration.total_layer)
        result = gdspy.boolean(result, P2_bridge, 'or', layer=self.layer_configuration.total_layer)
        self.layers.append(self.layer_configuration.total_layer)

        f = self.fluxline_params
        l, t_m, t_r, gap, l_arm, h_arm, s_gap = f['l'],f['t_m'],f['t_r'],f['gap'],f['l_arm'],f['h_arm'],f['s_gap']

        flux = PP_Squid_Fluxline(l, t_m, t_r, gap, l_arm, h_arm, s_gap,g = f.get('g'),w = f.get('w'),s = f.get('s'))

        fluxline = flux.render(self.center, self.w, self.h,self.g_h,self.g_t)['positive']

        self.couplers.append(flux)

        #removing ground where the fluxline is
        ground_fluxline =True
        if ground_fluxline == False:
            result = gdspy.boolean(result, gdspy.Rectangle((self.center[0]-l_arm/2-t_r-self.g_t,self.center[1]+self.h/2+0.01),(self.center[0]+3*l_arm/2+t_r+t_m+self.g_t,self.center[1]+self.h/2+250)), 'not', layer=self.layer_configuration.total_layer)
        else:
            result = gdspy.boolean(result, gdspy.Rectangle(
                (self.center[0] , self.center[1] + self.h / 2 + 0.01),
                (self.center[0] +  l_arm + t_m, self.center[1] + self.h / 2 + 250)), 'not',
                                   layer=self.layer_configuration.total_layer)


        result = gdspy.boolean(result, fluxline, 'or', layer=self.layer_configuration.total_layer)

        # add couplers
        last_step_cap = [gdspy.boolean(gdspy.boolean(P2, P2_bridge, 'or'),gdspy.boolean(P1, P1_bridge, 'or'),'or')]
        self.layers.append(self.layer_configuration.total_layer)

        # Box for inverted Polygons
        box = gdspy.Rectangle((self.center[0] - self.g_w / 2, self.center[1] - self.g_h / 2),(self.center[0] + self.g_w / 2, self.center[1] + self.g_h / 2))

        if len(self.couplers) != 0:
            for id, coupler in enumerate(self.couplers):
                if coupler.side == 'fluxline':
                    continue
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
                        qubit_cap_parts.append(gdspy.boolean(coupler.result_coupler, coupler.result_coupler, 'or',layer=10+id+self.secret_shift))
                        self.layers.append(10+id+self.secret_shift)
                        last_step_cap.append(coupler.result_coupler)
        qubit_cap_parts.append(gdspy.boolean(result,last_step_cap,'not'))

        inverted = gdspy.boolean(box, result, 'not',layer=self.layer_configuration.inverted)

        # add JJs
        if self.JJ_params is not None:
            self.JJ_coordinates = (self.center[0],self.center[1])
            JJ = self.generate_JJ()

        qubit = deepcopy(result)

        # set terminals for couplers
        self.set_terminals()

        if self.calculate_capacitance is False:
            qubit_cap_parts = None
            qubit = None
        if 'mirror' in self.transformations:
            return {'positive': result.mirror(self.transformations['mirror'][0], self.transformations['mirror'][1]),
                    'restrict': result_restricted,
                    'qubit': qubit.mirror(self.transformations['mirror'][0],
                                          self.transformations['mirror'][1]) if qubit is not None else None,
                    'qubit_cap': qubit_cap_parts,
                    'JJ': JJ.mirror(self.transformations['mirror'][0], self.transformations['mirror'][1]),
                    'inverted': inverted.mirror(self.transformations['mirror'][0], self.transformations['mirror'][1])
                    }
        if 'rotate' in self.transformations:
            return {'positive': result.rotate(self.transformations['rotate'][0], self.transformations['rotate'][1]),
                    'restrict': result_restricted,
                    'qubit': qubit.rotate(self.transformations['rotate'][0],
                                          self.transformations['rotate'][1]) if qubit is not None else None,
                    'qubit_cap': qubit_cap_parts,
                    'JJ': JJ.rotate(self.transformations['rotate'][0], self.transformations['rotate'][1]),
                    'inverted': inverted.rotate(self.transformations['rotate'][0], self.transformations['rotate'][1])
                    }
        elif self.transformations == {}:
            return {'positive': result,
                    'restrict': result_restricted,
                    'qubit': qubit,
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

        for key in self.remove_ground:
            if key == 'left':
                ground = gdspy.fast_boolean(ground,gdspy.Rectangle((z[0] - x / 2,z[1] - y / 2+t), (z[0] - x / 2 +t, z[1] + y / 2-t)) , 'not')
            if key == 'right':
                ground = gdspy.fast_boolean(ground,gdspy.Rectangle((z[0] + x / 2,z[1] - y / 2+t), (z[0] + x / 2 -t, z[1] + y / 2-t)) , 'not')
            if key == 'top':
                ground = gdspy.fast_boolean(ground,gdspy.Rectangle((z[0] - x / 2+t,z[1] + y / 2), (z[0] + x / 2-t, z[1] + y / 2-t)) , 'not')
            if key == 'bottom':
                ground = gdspy.fast_boolean(ground,gdspy.Rectangle((z[0] - x / 2+t,z[1] - y / 2), (z[0] + x / 2-t, z[1] - y / 2+t)) , 'not')

        return ground


    def set_terminals(self):
        for id, coupler in enumerate(self.couplers):

            if 'mirror' in self.transformations:
                if coupler.connection is not None:
                    coupler_connection = mirror_point(coupler.connection, self.transformations['mirror'][0], self.transformations['mirror'][1])
                    qubit_center = mirror_point(deepcopy(self.center), self.transformations['mirror'][0], self.transformations['mirror'][1])
                    if coupler.side == "left":
                        coupler_phi = np.pi
                    if coupler.side == "right":
                        coupler_phi = 0
                    if coupler.side == "top":
                        coupler_phi = -np.pi / 2
                    if coupler.side == "bottom":
                        coupler_phi = np.pi / 2
                    if coupler.side == 'fluxline':
                        coupler_phi = -np.pi / 2
            if 'rotate' in self.transformations:
                if coupler.connection is not None:
                    coupler_connection = rotate_point(coupler.connection, self.transformations['rotate'][0], self.transformations['rotate'][1])
                    qubit_center = rotate_point(deepcopy(self.center), self.transformations['rotate'][0], self.transformations['rotate'][1])
                    if coupler.side == "left":
                        coupler_phi = 0+np.arctan2(coupler_connection[1]-coupler.connection[1], coupler_connection[0]-coupler.connection[0])
                    if coupler.side == "right":
                        coupler_phi = np.pi+np.arctan2(coupler_connection[1]-coupler.connection[1], coupler_connection[0]-coupler.connection[0])
                    if coupler.side == "top":
                        coupler_phi = -np.pi / 2+np.arctan2(coupler_connection[1]-coupler.connection[1], coupler_connection[0]-coupler.connection[0])
                    if coupler.side == "bottom":
                        coupler_phi = np.pi / 2+np.arctan2(coupler_connection[1]-coupler.connection[1], coupler_connection[0]-coupler.connection[0])
                    if coupler.side == "fluxline":
                        coupler_phi = -np.pi / 2 + np.arctan2(coupler_connection[1] - coupler.connection[1],
                                                              coupler_connection[0] - coupler.connection[0])
            if self.transformations == {}:
                coupler_connection = coupler.connection
                if coupler.side == "left":
                    coupler_phi = 0
                if coupler.side == "right":
                    coupler_phi = np.pi
                if coupler.side == "top":
                    coupler_phi = -np.pi/2
                if coupler.side == "fluxline":
                    coupler_phi = -np.pi/2
                if coupler.side == "bottom":
                    coupler_phi = np.pi/2
            if coupler.connection is not None:

                self.terminals['coupler'+str(id)] = DesignTerminal(tuple(coupler_connection),
                                                                   coupler_phi, g=coupler.g, s=coupler.s,
                                                                w=coupler.w, type='cpw')
        return True


    def get_terminals(self):
        return self.terminals




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

    def add_to_tls(self, tls_instance: tlsim.TLSystem, terminal_mapping: dict, track_changes: bool = True, cutoff: float = np.inf) -> list:
        #scaling factor for C
        scal_C = 1e-15
        JJ = tlsim.Inductor(self.L)
        C = tlsim.Capacitor(c=self.C['qubit']*scal_C, name=self.name+' qubit-ground')
        tls_instance.add_element(JJ, [0, terminal_mapping['qubit']])
        tls_instance.add_element(C, [0, terminal_mapping['qubit']])
        mut_cap = []
        cap_g = []
        for id, coupler in enumerate(self.couplers):
            if coupler.coupler_type == 'coupler':
                c0 = tlsim.Capacitor(c=self.C['coupler'+str(id)][1]*scal_C, name=self.name+' qubit-coupler'+str(id)+self.secret_shift)
                c0g = tlsim.Capacitor(c=self.C['coupler'+str(id)][0]*scal_C, name=self.name+' coupler'+str(id)+'-ground'+self.secret_shift)
                tls_instance.add_element(c0, [terminal_mapping['qubit'], terminal_mapping['coupler'+str(id)+self.secret_shift]])
                tls_instance.add_element(c0g, [terminal_mapping['coupler'+str(id)+self.secret_shift], 0])
                mut_cap.append(c0)
                cap_g.append(c0g)
            # elif coupler.coupler_type =='grounded':
            #     tls_instance.add_element(tlsim.Short(), [terminal_mapping['flux line'], 0])

        if track_changes:
            self.tls_cache.append([JJ, C]+mut_cap+cap_g)
        return [JJ, C]+mut_cap+cap_g


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
    def __init__(self, l1,l2,t,side = 'left',coupler_type = 'none',heightl = 1,heightr=1,w= None, g=None, s=None):
        self.l1 = l1
        self.l2 = l2
        self.t = t
        self.gap = s
        self.side = side
        self.coupler_type = coupler_type
        self.ground_t = 0 # the lenght of the coupler connection part to the resonator
        self.height_left = heightl
        self.height_right = heightr
        self.connection = None
        #for defining the terminals
        self.w = w
        self.g = g
        self.s = s

    def render(self, center, g_w,g_h):
        result = 0
        if self.side == "left":
            result = gdspy.Rectangle((center[0]-g_w/2-self.t-self.gap,center[1]-self.height_left*g_h/2-self.gap),(center[0]-g_w/2-self.gap,center[1]+self.height_left*g_h/2+self.gap))
            if self.height_left == 1:
                upper  = gdspy.Rectangle((center[0]-g_w/2-self.t-self.gap,center[1]+g_h/2+self.gap),(center[0]-g_w/2+self.l1-self.gap-self.t,center[1]+g_h/2+self.t+self.gap))
                lower  = gdspy.Rectangle((center[0]-g_w/2-self.t-self.gap,center[1]-g_h/2-self.gap-self.t),(center[0]-g_w/2+self.l2-self.gap-self.t,center[1]-g_h/2-self.gap))
            line   = gdspy.Rectangle((center[0]-g_w/2-self.t-self.gap-self.gap-self.ground_t,center[1]-self.w/2),(center[0]-g_w/2-self.t-self.gap,center[1]+self.w/2))#modified here ;), remove ground_t
            if self.height_left ==1:
                result = gdspy.boolean(result, upper, 'or')
                result = gdspy.boolean(result, lower, 'or')
            result = gdspy.boolean(result, line, 'or')

            self.connection = (center[0]-g_w/2-self.t-self.gap-self.gap,center[1])


        if self.side == "right":
            result = gdspy.Rectangle((center[0]+g_w/2+self.t+self.gap,center[1]-self.height_right*g_h/2-self.gap),(center[0]+g_w/2+self.gap,center[1]+self.height_right*g_h/2+self.gap))
            if self.height_right == 1:
                upper  = gdspy.Rectangle((center[0]+g_w/2+self.t+self.gap,center[1]+g_h/2+self.gap),(center[0]+g_w/2-self.l1+self.gap+self.t,center[1]+g_h/2+self.t+self.gap))
                lower  = gdspy.Rectangle((center[0]+g_w/2+self.t+self.gap,center[1]-g_h/2-self.gap-self.t),(center[0]+g_w/2-self.l2+self.gap+self.t,center[1]-g_h/2-self.gap))

            line = gdspy.Rectangle((center[0]+g_w/2+self.t+self.gap+self.gap,center[1]-self.w/2),(center[0]+g_w/2+self.t+self.gap,center[1]+self.w/2))
            if self.height_right == 1:
                result = gdspy.boolean(result, upper, 'or')
                result = gdspy.boolean(result, lower, 'or')
            result = gdspy.boolean(result, line, 'or')

            self.connection = (center[0] + g_w / 2 + self.t + self.gap + self.gap, center[1] )

        if self.side == "top":
            result = gdspy.Rectangle((center[0]-g_w/2+self.l1,center[1]+g_h/2+self.gap),(center[0]-g_w/2+self.l1+self.l2,center[1]+g_h/2+self.gap+self.t))
            line   = gdspy.Rectangle((center[0]-g_w/2+self.l1+self.l2/2-self.w/2,center[1]+g_h/2+self.gap+self.t),(center[0]-g_w/2+self.l1+self.l2/2+self.w/2,center[1]+g_h/2+self.gap+self.t+self.gap))
            result = gdspy.boolean(result, line, 'or')
            self.connection = (center[0]-g_w/2+self.l1+self.l2/2, center[1]+g_h/2+self.gap+self.t+self.gap)

        if self.side == "bottom":
            result = gdspy.Rectangle((center[0]-g_w/2+self.l1,center[1]-g_h/2-self.gap),(center[0]-g_w/2+self.l1+self.l2,center[1]-g_h/2-self.gap-self.t))
            line   = gdspy.Rectangle((center[0]-g_w/2+self.l1+self.l2/2-self.w/2,center[1]-g_h/2-self.gap-self.t),(center[0]-g_w/2+self.l1+self.l2/2+self.w/2,center[1]-g_h/2-self.gap-self.t-self.gap))
            result = gdspy.boolean(result, line, 'or')
            self.connection = (center[0]-g_w/2+self.l1+self.l2/2, center[1]-g_h/2-self.gap-self.t-self.gap)

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
    def __init__(self, l,t_m,t_r,gap,l_arm,h_arm,s_gap,w= None, g=None, s=None):
        self.l      = l
        self.t_m    = t_m
        self.t_r    = t_r
        self.gap    = gap
        self.l_arm  = l_arm
        self.h_arm  = h_arm
        self.s_gap  = s_gap
        self.side   = 'fluxline'
        self.connection = None
        #for the terminals:
        self.g = g
        self.w = w
        self.s = s

    def render(self, center, width,height,ground_height,ground_t):
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

        result = gdspy.boolean(result,gdspy.Rectangle(
                (center[0] , center[1] + ground_height / 2 - ground_t),
                (center[0] +  self.l_arm + self.t_m, center[1] + ground_height / 2 + 250)),'not')

        result = gdspy.boolean(result,gdspy.Rectangle(
                (center[0] -2*self.l_arm, center[1] + ground_height / 2 ),
                (center[0] +2*self.l_arm, center[1] + ground_height / 2 +100)),'not')

        self.result_coupler = result

        self.connection = (center[0]+self.l_arm/2+self.t_m/2, center[1]+ground_height/2-ground_t)
        return {
            'positive': result
                        }

def mirror_point(point,ref1,ref2):
    """
       Mirror a point by a given line specified by 2 points ref1 and ref2.
    """
    [x1, y1] =ref1
    [x2, y2] =ref2

    dx = x2-x1
    dy = y2-y1
    a = (dx * dx - dy * dy) / (dx * dx + dy * dy)
    b = 2 * dx * dy / (dx * dx + dy * dy)
    x2 = round(a * (point[0] - x1) + b * (point[1] - y1) + x1)
    y2 = round(b * (point[0] - x1) - a * (point[1] - y1) + y1)
    return x2, y2


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
