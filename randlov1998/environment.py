import numpy as np
from scipy import asarray

from numpy import sin, cos, tan, sqrt, arcsin, arctan, sign

from pybrain.rl.environments.graphical import GraphicalEnvironment

# TODO consider moving some calculations, like psi, from the environment to the
# task. psi seems particularly task-dependent.
class Environment(GraphicalEnvironment):
    # TODO RL-state is [theta, thetad, omega, omegad, omegadd]^T

    # For superclass.
    indim = 2
    outdim = 10

    # Environment parameters.
    time_step = 0.01
    
    # Goal position and radius
    # Lagouakis (2002) uses angle to goal, not heading, as a state
    r_goal = 5.
    max_distance = 1000.
    
    # last state storage variables
    last_xf = 0
    last_yf = 0
    last_omega = 0
    last_psig = 0

    # Acceleration on Earth's surface due to gravity (m/s^2):
    g = 9.82
    
    # See the paper for a description of these quantities:
    # Distances (in meters):
    c = 0.66
    dCM = 0.30
    h = 0.94
    L = 1.11
    r = 0.34
    # Masses (in kilograms):
    Mc = 15.0
    Md = 1.7
    Mp = 60.0
    # Velocity of a bicycle (in meters per second), equal to 10 km/h:
    v = 10.0 * 1000.0 / 3600.0
    
    # Derived constants.
    M = Mc + Mp # See Randlov's code.
    Idc = Md * r**2
    Idv = 1.5 * Md * r**2
    Idl = 0.5 * Md * r**2
    Itot = 13.0 / 3.0 * Mc * h**2 + Mp * (h + dCM)**2
    sigmad = v / r

    def __init__(self, randomInitState, x_goal, y_goal):
        GraphicalEnvironment.__init__(self)
        self.x_goal = x_goal
        self.y_goal = y_goal
        self.randomInitState = randomInitState
        self.reset()
        self.actions = [0.0, 0.0]
        self._save_wheel_contact_trajectories = False

    def getSteer(self):
        return self.sensors[0]

    def getTilt(self):
        return self.sensors[2]

    def getXF(self):
        return self.sensors[5]

    def getYF(self):
        return self.sensors[6]

    def getXB(self):
        return self.sensors[7]

    def getYB(self):
        return self.sensors[8]
        
    def getPSI(self):
        return self.sensors[9]
     
    def getPSIG(self):
        return self.sensors[10]    

    def get_xfhist(self):
        return self.xfhist

    def get_yfhist(self):
        return self.yfhist

    def get_xbhist(self):
        return self.xbhist

    def get_ybhist(self):
        return self.ybhist

    def getSensors(self):
        return self.sensors

    def performAction(self, actions):
        self.actions = actions
        self.step()

    def saveWheelContactTrajectories(self, opt):
        self._save_wheel_contact_trajectories = opt

    def step(self):
        # Unpack the state and actions.
        # -----------------------------
        # Want to ignore the previous value of omegadd; it could only cause a
        # bug if we assign to it.
        
        (theta, thetad, omega, omegad, _,
                xf, yf, xb, yb, psi, psig) = self.sensors
        (T, d) = self.actions

        # store a last states 
        self.last_xf = xf
        self.last_yf = yf
        self.last_omega = omega
        self.last_psig = psig
        
        # For recordkeeping.
        # ------------------
        if self._save_wheel_contact_trajectories:
            self.xfhist.append(xf)
            self.yfhist.append(yf)
            self.xbhist.append(xb)
            self.ybhist.append(yb)

        # Process the actions.
        # --------------------
        # TODO Add noise to the inputs, as Randlov did.
        # d_noised += 0.04 * (0.5 - np.random.rand())
        # Control should be trivial otherwise.

        # Intermediate time-dependent quantities.
        # ---------------------------------------
        # Avoid divide-by-zero, just as Randlov did.
        if theta == 0:
            rf = 1e8
            rb = 1e8
            rCM = 1e8
        else:
            rf = self.L / np.abs(sin(theta))
            rb = self.L / np.abs(tan(theta))
            rCM = sqrt((self.L - self.c)**2 + self.L**2 / tan(theta)**2)

        phi = omega + np.arctan(d / self.h)

        # Equations of motion.
        # --------------------
        # Second derivative of angular acceleration:
        omegadd = 1 / self.Itot * (self.M * self.h * self.g * sin(phi)
                - cos(phi) * (self.Idc * self.sigmad * thetad
                    + sign(theta) * self.v**2 * (
                        self.Md * self.r * (1.0 / rf + 1.0 / rb)
                        + self.M * self.h / rCM)))
        thetadd = (T - self.Idv * self.sigmad * omegad) / self.Idl

        # Integrate equations of motion using Euler's method.
        # ---------------------------------------------------
        # yt+1 = yt + yd * dt.
        # Must update omega based on PREVIOUS value of omegad.
        omegad += omegadd * self.time_step
        omega += omegad * self.time_step
        thetad += thetadd * self.time_step
        theta += thetad * self.time_step

        # Handlebars can't be turned more than 80 degrees.
        theta = np.clip(theta, -1.3963, 1.3963)

        # Wheel ('tyre') contact positions.
        # ---------------------------------

        # Front wheel contact position.
        front_temp = self.v * self.time_step / (2 * rf)
        # See Randlov's code.
        if front_temp > 1:
            front_temp = sign(psi + theta) * 0.5 * np.pi
        else:
            front_temp = sign(psi + theta) * arcsin(front_temp)
        xf += self.v * self.time_step * -sin(psi + theta + front_temp)
        yf += self.v * self.time_step * cos(psi + theta + front_temp)

        # Rear wheel.
        back_temp = self.v * self.time_step / (2 * rb)
        # See Randlov's code.
        if back_temp > 1:
            back_temp = np.sign(psi) * 0.5 * np.pi
        else:
            back_temp = np.sign(psi) * np.arcsin(back_temp)
        xb += self.v * self.time_step * -sin(psi + back_temp)
        yb += self.v * self.time_step * cos(psi + back_temp)

        # Preventing numerical drift.
        # ---------------------------
        # Copying what Randlov did.
        current_wheelbase = sqrt((xf - xb)**2 + (yf - yb)**2)
        if np.abs(current_wheelbase - self.L) > 0.01:
            relative_error = self.L / current_wheelbase - 1.0
            xb += (xb - xf) * relative_error
            yb += (yb - yf) * relative_error

        # Update heading, psi.
        # --------------------
        delta_y = yf - yb
        if (xf == xb) and delta_y < 0.0:
            psi = np.pi
        else:
            if delta_y > 0.0:
                psi = arctan((xb - xf) / delta_y)
            else:
                # TODO we inserted this ourselves:
                #delta_x = xb - xf
                #if delta_x == 0:
                #    dy_by_dx = np.sign(delta_y) * np.inf
                #else:
                #    dy_by_dx = delta_y / delta_x
                psi = sign(xb - xf) * 0.5 * np.pi - arctan(delta_y / (xb - xf))
               # dy_by_dx))
        
        # Update angle to goal, psig (Lagoudakis, 2002, calls this "psi")
        # --------------------
        yg = self.y_goal
        xg = self.x_goal
        delta_yg = yg - yb
        if (xg == xb) and delta_yg < 0.0:
            psig = psi - np.pi
        else:
            if delta_y > 0.0:
                psig = psi - ( arctan((xb - xg) / delta_yg) )
            else:
                psig = psi - (sign(xb - xg) * 0.5 * np.pi - arctan(delta_yg / (xb - xg)) )

        self.sensors = np.array([theta, thetad, omega, omegad, omegadd,
                xf, yf, xb, yb, psi, psig])

        if self.hasRenderer():
            self.getRenderer().updateData(self.sensors)
            


    def reset(self):
        # Lagoudakis (2002) randomizes the initial state "arout the 
        # equilibrium position"

        if self.randomInitState:
            theta = np.random.normal(0,1)*np.pi/180
            thetad = 0
            #thetad = np.random.normal(0,2)
            omega = np.random.normal(0,1)*np.pi/180
            #omegad = np.random.normal(0,2)
            #omegadd = np.random.normal(0,2)
            omegad = 0
            omegadd = 0
            # randomize rear tire location
            #xb = np.random.normal(0,10)
            #yb = np.random.normal(0,10)
            
            xb = 0
            yb = 0
            xf  = xb + (np.random.rand(1)*self.L - 0.5*self.L)
            yf = np.sqrt(self.L**2 - (xf-xb)**2) + yb
            
            #print 'DEBUG: Random init states'
            #print theta, thetad, omega, omegad, omegadd
            #print xb, yb, xf, yf
        
        else:   
            theta = 0
            thetad = 0
            omega = 0
            omegad = 0
            omegadd = 0
            xf = 0
            yf = self.L
            xb = 0
            yb = 0
        
        psi = np.arctan((xb - xf) / (yf - yb))
        psig = psi - np.arctan((xb - self.x_goal) / (self.y_goal - yb))
        self.sensors = np.array([theta, thetad, omega, omegad, omegadd,
                xf, yf, xb, yb, psi, psig])
        self.xfhist = []
        self.yfhist = []
        self.xbhist = []
        self.ybhist = []
