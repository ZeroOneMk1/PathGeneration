import math, Utility, random

STEP_TIME = 0.02 # 20 millisecond cycle time
K_P_TRANS = 30
K_P_ROT = 1
STOP_DISTANCE_THRESHOLD = 1 # In inches, pathfinding algo terminates when distance to destination dips below threshold
POSITION_NOISE = 0.1 # position noise in inches that cna be generated at each timestep. triangular distribution with [-POSITION_NOISE, POSITION_NOISE]

MAX_TRANS_ACCEL= 120 # in/s^2
MAX_ROT_ACCEL = 100 # deg/s^2
MAX_SPEED = 60 # in/s

# convert to accel per timestep, which is 20 msec
MAX_TRANS_ACCEL *= 0.02
MAX_ROT_ACCEL *= 0.02

# A point at some timestep in the simulation, generated numerically from some pathfinding algorithm, which can differ slightly from the theoretical trajectory
class SimulationPoint:
    def __init__(self, x, y, theta, **kwargs):
        self.x = x
        self.y = y
        self.theta = theta

        self.__dict__.update(kwargs) # handy way to store any keyword arguments as instance variables

# Abstract
class GenericRobot:

    def __init__(self, width, length):
        self.width = width
        self.length = length
        self.simulation = None

    def computeSimulation(self, points):
        raise NotImplementedError("Must implement this function")

    def startSimulation(self, points):

        # Calculate curvature of each point
        points[0].curve = 0
        points[-1].curve = 0
        for i in range(1, len(points) - 1):
            angle = math.atan2(points[i+1].y - points[i-1].y, points[i+1].x - points[i-1].x) - math.atan2(points[i].y - points[i-1].y, points[i].x - points[i-1].x)
            if angle > math.pi:
                angle -= 2*math.pi
            points[i].curve = abs(angle)

        self.simulation = self.computeSimulation(points)
        return len(self.simulation)

    # return if animation is still going
    def simulationTick(self, screen, m, pointIndex):

        if pointIndex == len(self.simulation):
            return False
        
        p = self.simulation[pointIndex]
        cx, cy = m.inchToPixel(p.x, p.y)
        theta = p.theta
        width = self.width * m.zoom
        length = self.length * m.zoom

        dxw = math.cos(theta + math.pi/2) * width
        dyw = math.sin(theta + math.pi/2) * width
        dxl = math.cos(theta) * length
        dyl = math.sin(theta) * length

        # Generate four points of a rectangle around (cx, cy) given some heading
        points = [
            (cx - dxw - dxl, cy - dyw - dyl),
            (cx + dxw - dxl, cy + dyw - dyl),
            (cx + dxw + dxl, cy + dyw + dyl),
            (cx - dxw + dxl, cy - dyw + dyl),
        ]

        s = m.getPartialZoom(0.5)
        Utility.drawPolygon(screen, Utility.BLACK, points, 3 * s)

        # Draw arrow
        tx = cx + math.cos(theta)*length * 0.4
        ty = cy + math.sin(theta)*length * 0.4
        Utility.drawLine(screen, Utility.BLACK, cx, cy, tx, ty, 4  * s)
        Utility.drawPolarTriangle(screen, Utility.BLACK, tx, ty, theta, 7 * s, 1, math.pi / 2)

        # Draw timestamp
        Utility.drawText(screen, Utility.getFont(30), "Current: {}s".format(round(pointIndex * STEP_TIME, 2)), Utility.BLACK, 30, 60, 0)
        Utility.drawText(screen, Utility.getFont(30), "Total: {}s".format(round(len(self.simulation) * STEP_TIME, 2)), Utility.BLACK, 30, 90, 0)

        return True

class IdealRobot(GenericRobot):

    def __init__(self, width, height):
        super().__init__(width, height)

    # With an ideal robot, the robot's actual position in each timestep is what it is supposed to be
    def computeSimulation(self, points):
        return [SimulationPoint(p.x, p.y, p.theta) for p in points]

class PurePursuitRobot(GenericRobot):

    # lookahead in inches
    # acceleration limits in inches/seconds^2
    def __init__(self, width, height, lookahead):
        super().__init__(width, height)
        self.lookahead = lookahead

    # Find closest point to (x,y) in points, from index range [start, end)
    # Returns index of closest point in points lis
    def findClosestPoint(self, points, x, y, start, end):

        start = max(start, 0)
        end = min(end, len(points) - 1)

        minIndex = start
        minDist = Utility.distance(x, y, points[start].x, points[start].y)
        start += 1
        while start < end:
            dist = Utility.distance(x, y, points[start].x, points[start].y)
            if dist < minDist:
                minIndex = start
                minDist = dist
            start += 1

        return minIndex

    # starting x, y, theta
    def computeSimulation(self, points):

        MAX_TIMESTEPS = 50000
        timestep = 0

        simulation = []

        # Start pose, which has inbuilt noise
        x = points[0].x + 10 * random.triangular(-POSITION_NOISE, POSITION_NOISE)
        y = points[0].y + 10 * random.triangular(-POSITION_NOISE, POSITION_NOISE)
        theta = points[0].theta
        
        xvel = 0 # velocities in inches/second
        yvel = 0
        tvel = 0 # angular velocity
        li = 0 # lookahead index
        ci = 0 # closest index

        while li != len(points) - 1 or Utility.distance(points[-1].x, points[-1].y, x, y) > STOP_DISTANCE_THRESHOLD or abs(xvel) > 5 or abs(yvel) > 5 or abs(tvel) > 5:

            if timestep > MAX_TIMESTEPS:
                break

            # Find closest waypoint within 5 points of the current waypoint
            ci = self.findClosestPoint(points, x, y, ci, ci + 30)
        
            # Update lookahead distance
            while li < len(points) - 1 and Utility.distance(points[li].x, points[li].y, points[ci].x, points[ci].y) < self.lookahead:
                li += 1

             # Calculate target velocities
            targetXVel = (points[li].x - x) * K_P_TRANS
            targetYVel = (points[li].y - y) * K_P_TRANS

            # Constrain maximum robot speed
            mag = Utility.hypo(targetXVel, targetYVel)
            scalar = min(1, MAX_SPEED / mag)
            targetXVel *= scalar
            targetYVel *= scalar
            
            # Calculate heading delta (turn the fastest way)
            dtheta = (points[li].theta - theta) % (2*math.pi)
            if dtheta > math.pi:
                dtheta -= 2*math.pi
            targetTVel = dtheta * K_P_ROT

            # I'd constrain individual wheel accelerations here but I don't know mecanum kinematics yet

            # Update velocities given target velocities, and constrain with acceleration limits
            xvel += Utility.clamp(targetXVel - xvel, -MAX_TRANS_ACCEL, MAX_TRANS_ACCEL)
            yvel += Utility.clamp(targetYVel - yvel, -MAX_TRANS_ACCEL, MAX_TRANS_ACCEL)
            tvel += Utility.clamp(targetTVel - tvel, -MAX_ROT_ACCEL, MAX_ROT_ACCEL)

            # Update distance from actual velocity
            x += xvel * STEP_TIME + random.triangular(-POSITION_NOISE, POSITION_NOISE) # add positional noise to simulation for realism 
            y += yvel * STEP_TIME + random.triangular(-POSITION_NOISE, POSITION_NOISE)
            theta += tvel * STEP_TIME

            # Add timestep to simulation
            simulation.append(SimulationPoint(x, y, theta,
                                              xvel = xvel, yvel = yvel, tvel = tvel, cx = points[ci].x, cy = points[ci].y, lx = points[li].x, ly = points[li].y, curve = points[li].curve))
            timestep += 1

        return simulation

    
    # Override generic simulationTick by drawing stats and lookahead line
    def simulationTick(self, screen, m, pointIndex):

        ret = super().simulationTick(screen, m, pointIndex)

        # Draw position and velocity stats
        p = self.simulation[pointIndex]
        Utility.drawText(screen, Utility.getFont(30), "Pure Pursuit", Utility.BLACK, 200, 30, 0)
        Utility.drawText(screen, Utility.getFont(20), "xpos: {} inch".format(round(p.x, 2)), Utility.BLACK, 200, 50, 0)
        Utility.drawText(screen, Utility.getFont(20), "ypos: {} inch".format(round(p.y, 2)), Utility.BLACK, 200, 65, 0)
        Utility.drawText(screen, Utility.getFont(20), "theta: {} deg".format(round(p.theta * 180 / math.pi, 2)), Utility.BLACK, 200, 80, 0)
        Utility.drawText(screen, Utility.getFont(20), "xvel: {} inch/sec".format(round(p.xvel, 2)), Utility.BLACK, 330, 50, 0)
        Utility.drawText(screen, Utility.getFont(20), "yvel: {} inch/sec".format(round(p.yvel, 2)), Utility.BLACK, 330, 65, 0)
        Utility.drawText(screen, Utility.getFont(20), "tvel: {} deg/sec".format(round(p.tvel * 180 / math.pi, 2)), Utility.BLACK, 330, 80, 0)

        Utility.drawText(screen, Utility.getFont(20), "Curve: {}".format(round(p.curve, 3)), Utility.BLACK, 200, 95, 0)

        # Draw lookahead line

        lx, ly = m.inchToPixel(p.lx, p.ly)
        Utility.drawCircle(screen, *m.inchToPixel(p.cx, p.cy), Utility.ORANGE, 2)
        Utility.drawLine(screen, Utility.GREEN, *m.inchToPixel(p.x, p.y), lx, ly, 2)
        Utility.drawCircle(screen, lx, ly, Utility.GREEN, 2)
        
        return ret
        
    
