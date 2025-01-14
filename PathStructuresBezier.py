from enum import Enum
from termios import VT1
import Utility
import math
import pygame
import SplineCurves
import BezierCurves
import Robot


class Pose:

    RADIUS = 6

    # units are in SCREEN PIXELS (which would be converted to inches during export) and theta is in degrees (0-360)
    def __init__(self, x, y, forward_x_pt, forward_y_pt, theta = None):
        self.x = x
        self.y = y
        
        self.setVectorOffset(forward_x_pt, forward_y_pt)
        
        # temp = (self.forward_y - self.y) / (self.forward_x - self.x)

        self.theta = theta

        self.hovered = False
        self.showCoords = False
        # a break pose is a stopping pose where poses on one side of this pose don't affect the other
        self.isBreak = False

    def setVectorOffset(self, forward_x_pt, forward_y_pt):
        
        self.forward_x = forward_x_pt - self.x
        self.backward_x = self.x - forward_x_pt

        self.forward_y = forward_y_pt - self.y
        self.backward_y = self.y - forward_y_pt

    def touching(self, m):
        return Utility.distance(self.x, self.y, m.zx, m.zy) <= (Pose.RADIUS - 1) / m.zoom

    def draw(self, screen, m, forceOrange=False):

        r = (Pose.RADIUS + 2 if self.hovered else Pose.RADIUS) * \
            m.getPartialZoom(0.75)

        if forceOrange:
            color = Utility.ORANGE
            r += 3
        else:
            color = Utility.RED if self.isBreak else Utility.GREEN

        p1 = m.inchToPixel(self.x - self.forward_x, self.y - self.forward_y)
        p2 = m.inchToPixel(self.x + self.forward_x , self.y + self.forward_y)
        Utility.drawVector(screen, *p1, *p2, m.getPartialZoom(0.75))

        x, y = m.inchToPixel(self.x, self.y)

        #  draw triangle
        if self.theta is not None:
            Utility.drawPolarTriangle(
                screen, Utility.BLACK, x, y, self.theta, r, 2.3, 0.9)

        Utility.drawCircle(screen, x, y, color, r)

        if self.showCoords or self.hovered:
            string = "({},{})".format(round(self.x, 1), round(self.y, 1))
            Utility.drawText(screen, Utility.getFont(23 * m.getPartialZoom(0.75)),
                             string, Utility.TEXTCOLOR, x, y - 25*m.getPartialZoom(0.75))



# Each point is generated through interpolating between poses
class Point:
    def __init__(self, x: int, y: int, color):
        self.x = x
        self.y = y
        self.color = color


class Path:

    def __init__(self, segmentDistance):

        self.poses = []
        self.points = []

        self.robot = Robot.PurePursuitRobot(50, 30)
        #self.robot = Robot.IdealRobot(50, 30)

        self.segmentDistance = segmentDistance

        self.pathIndex = -1

    def getPoseIndex(self, pose):
        index = -1
        for i in range(len(self.poses)):
            if self.poses[i] == pose:
                index = i
                break
        return index

    def deletePose(self, index):
        if type(index) is not int:
            index = self.getPoseIndex(index)
        if index == -1:
            return

        if index == 0 and len(self.poses) > 1 and self.poses[1].theta is None:
            self.poses[1].theta = self.poses[0].theta
        del self.poses[index]

    def getTouchingPathIndex(self, x, y):

        if len(self.poses) == 0:
            return -1

        x1 = self.poses[0].x
        y1 = self.poses[0].y

        for i in range(1, len(self.poses)):

            x2 = self.poses[i].x
            y2 = self.poses[i].y

            if Utility.pointTouchingLine(x, y, x1, y1, x2, y2, 3):
                return i - 1

            x1 = x2
            y1 = y2

        return -1

    def handleMouseHeading(self, m):

        if not m.pressing:
            m.poseSelectHeading = None

        # update heading for pose
        if m.poseSelectHeading is not None:
            p = m.poseSelectHeading
            px, py = m.inchToPixel(p.x, p.y)

            if m.selectVectorNotHeading:

                # Set control point to mouse
                if Utility.distance(m.zx, m.zy, p.x, p.y) > 1: # control point must be at least one inch away from pose
                    p.setVectorOffset(m.zx, m.zy)
                    self.interpolatePoints()
                
            else: # Set robot heading to mouse
                # for close distances, remove heading. But first MUST have heading
                if p is not self.poses[0] and Utility.distance(m.x, m.y, px, py) < Pose.RADIUS*2:
                    p.theta = None
                else:  # Otherwise, get heading from normalized vector from center to mouse
                    p.theta = math.atan2(m.y - py, m.x - px)

                self.interpolatePoints()

    def handleHoveringOverPoses(self, m):

        anyHovered = False

        if m.x < Utility.SCREEN_SIZE and m.poseDragged is None and m.poseSelectHeading is None:
            for pose in self.poses:
                if pose.touching(m):
                    anyHovered = True
                    pose.hovered = True

                    if m.pressedR and not m.simulating:
                        pose.isBreak = not pose.isBreak
                        self.interpolatePoints()

                    if not m.simulating and m.getKey(pygame.K_x) and not m.getKey(pygame.K_c):
                        self.deletePose(pose)
                        self.interpolatePoints()
                    elif m.pressed and m.poseDragged is None:
                        if (m.getKey(pygame.K_c) or m.getKey(pygame.K_v)) and not m.simulating:
                            m.poseSelectHeading = pose
                            m.selectVectorNotHeading = m.getKey(pygame.K_v)
                        else:
                            m.poseDragged = pose
                            m.startDragX = m.x
                            m.startDragY = m.y
                            
                else:
                    pose.hovered = False

        return anyHovered


    def handleSimulation(self, m, slider):

        # Handle auto-calibration
        if m.simulating and m.getKey(pygame.K_RETURN) and len(self.points) > 0:
            if isinstance(self.robot, Robot.PurePursuitRobot):
                self.robot.autoCalibrate(m, slider)

        # Handle start simulation
        if m.getKeyPressed(pygame.K_SPACE) and len(self.points) > 0:

            if m.simulating:  # Toggle playback
                if slider.value == slider.high:
                    slider.reset()
                    m.playingSimulation = True
                else:
                    m.playingSimulation = not m.playingSimulation
            else:
                self.robot.startSimulation(m, slider, self.points)

        # Handle stop simulation
        if m.getKey(pygame.K_ESCAPE):
            m.simulating = False

    def handlePlayback(self, m, slider):

        if m.simulating and m.playingSimulation:
            if slider.value == slider.high:
                m.playingSimulation = False
            else:
                slider.value += 1
                slider.updateXFromIndex()

    def handleMouse(self, m, slider):
        self.handleSimulation(m, slider)

        # Handle scrolling the field
        if not m.pressing:
            m.panning = False
        if m.panning:
            dx = m.x - m.prevX
            dy = m.y - m.prevY
            m.panX += dx
            m.panY += dy
            m.boundFieldPan()
        self.handleMouseHeading(m)

        # Update dragging and handle toggling showCoords
        if m.poseDragged is not None:

            if m.pressing and not m.simulating:
                if m.startDragX != m.x or m.startDragY != m.y:  # make sure mouse actually has moved
                    m.poseDragged.x = min(m.pixelToInch(
                        Utility.SCREEN_SIZE, 0)[0], m.zx)
                    m.poseDragged.y = m.zy
                    self.interpolatePoints()

            if not m.pressing:
                if m.released and m.startDragX == m.x and m.startDragY == m.y:
                    m.poseDragged.showCoords = not m.poseDragged.showCoords

                m.poseDragged = None

        anyHovered = self.handleHoveringOverPoses(m)

        self.pathIndex = -1 \
            if (anyHovered or m.poseSelectHeading is not None) else self.getTouchingPathIndex(
                m.zx, m.zy)


        if self.pathIndex != -1:

            # Delete node closest to mouse if edge hovered and pressed X
            if not m.simulating and not anyHovered and m.getKey(pygame.K_x) and not m.getKey(pygame.K_c):

                # delete everything if only 2 poses and deleting the edge between them
                if len(self.poses) == 2:
                    self.poses = []
                    self.points = []
                else:
                    print(self.pathIndex, len(self.poses))
                    p1 = self.poses[self.pathIndex]
                    p2 = self.poses[self.pathIndex + 1]
                    distTo1 = Utility.distance(m.zx, m.zy, p1.x, p1.y)
                    distTo2 = Utility.distance(m.zx, m.zy, p2.x, p2.y)
                    index = self.pathIndex if distTo1 < distTo2 else self.pathIndex + 1
                    self.deletePose(index)
                    self.interpolatePoints()
                self.pathIndex = -1  # now that it's deleted, the mouse is not hovering over any path

        if not anyHovered and m.x < Utility.SCREEN_SIZE:
            if m.pressedR and not m.getKey(pygame.K_c) and not m.simulating:
                self.addPose(m.zx, m.zy, m.zx + 3, m.zy + 3)
                m.poseSelectHeading = self.poses[-1]
                m.selectVectorNotHeading = True
            if m.pressed:
                m.panning = True
                
        
        return anyHovered

    def getMousePosePosition(self, x, y):

        if self.pathIndex == -1:
            return (x, y)
        else:
            p1, p2 = self.poses[self.pathIndex], self.poses[self.pathIndex+1]
            return Utility.pointOnLineClosestToPoint(x, y, p1.x, p1.y, p2.x, p2.y)

    def addPose(self, x, y, fx, fy):

        px, py = self.getMousePosePosition(x, y)

        if self.pathIndex == -1:  # add to the end

            # only the first pose has a predefined position (pointing up)
            self.poses.append(Pose(px, py, fx, fy, -math.pi/2 if len(self.poses) == 0 else None))

        else:  # insert between two poses

            self.poses.insert(self.pathIndex + 1, Pose(px, py, fx, fy))

        self.interpolatePoints()

    def drawPaths(self, screen, m):

        if len(self.poses) == 0:
            return

        for i in range(1, len(self.poses)):
            color = Utility.LINEDARKGREY if (
                self.pathIndex == i-1) else Utility.LINEGREY
            Utility.drawLine(screen, color, *m.inchToPixel(self.poses[i-1].x, self.poses[i-1].y), *m.inchToPixel(
                self.poses[i].x, self.poses[i].y), 3 * m.getPartialZoom(0.75))

        first = True
        for pose in self.poses:
            pose.draw(screen, m, first)
            first = False


    # Interpolate pose[i] to pose[i+1] using Catmull-Rom spline curve with s spillover
    def interpolateSplineCurve(self, i: int, s: int) -> int:
        P1 = [self.poses[i].x, self.poses[i].y]
        V1 = [self.poses[i].forward_x, self.poses[i].forward_y]
        V2 = [self.poses[i+1].backward_x, self.poses[i+1].backward_y]
        P2 = [self.poses[i+1].x, self.poses[i+1].y]

        if s == 0:
            ns = 0
        else:
            dxds,dyds = BezierCurves.getBezierGradient(0, P1, [V1[0], V1[1]], [V2[0], V2[1]], P2)
            dsdt = s / Utility.hypo(dxds, dyds)
            ns = dsdt # s normalized from 0 to 1 for this specific spline
            if ns > 1:
                return ns - 1 # no points on this spline segment

        while ns < 1:
            x, y = BezierCurves.getBezierPoint(ns, P1, [V1[0], V1[1]], [V2[0], V2[1]], P2)
            self.points.append(Point(x, y, Utility.RED))

            dxds, dyds = BezierCurves.getBezierGradient(ns, P1, [V1[0], V1[1]], [V2[0], V2[1]], P2)
            dsdt = self.segmentDistance / Utility.hypo(dxds, dyds)
            ns += dsdt

        s = self.segmentDistance - Utility.distance(x,y,*P2)
        return s

    # Interpolate between all the *given* thetas, as in some poses do not specify theta and should just be interpolated between the poses besides them
    def interpolateTheta(self, knownThetaIndexes):

        i1, theta1 = knownThetaIndexes[0]
        assert i1 == 0
        for ki in range(1, len(knownThetaIndexes)):
            i2, theta2 = knownThetaIndexes[ki]

            for i in range(0, i2-i1+1):
                # Eliminate mod "wraparounds" by always finding the closest direction to spin
                theta2adjusted = theta2
                if theta2 - theta1 >= math.pi:
                    theta2adjusted -= 2*math.pi
                elif theta1 - theta2 >= math.pi:
                    theta2adjusted += 2*math.pi
                    
                self.points[ i1 + i].theta = theta1 + (theta2adjusted - theta1) * (i / (i2-i1))    

            i1 = i2
            theta1 = theta2

        # For all the points past the last known theta index, just set theta to the same number
        for index in range(i1, len(self.points)):
            self.points[index].theta = theta1

    # Call this function to update self.points whenever there is a change in interpolation. Generates a list of points from the entire combined path
    def interpolatePoints(self) -> None:

        self.points = []
        # for the purposes of interpolating theta after initially generating list of points
        knownThetaIndexes = []

        if len(self.poses) < 2:
            return

        s = 0
        for i in range(len(self.poses) - 1):

            if self.poses[i].x == self.poses[i+1].x and self.poses[i].y == self.poses[i+1].y:
                continue

            # Mark point with theta if pose has specified theta
            if self.poses[i].theta is not None:
                knownThetaIndexes.append(
                    [len(self.points), self.poses[i].theta])

            s = self.interpolateSplineCurve(i, s)

            # no spillovers at break points
            if self.poses[i+1].isBreak:
                s = 0

        # Mark last point with theta if it exists
        if self.poses[-1].theta is not None:
            knownThetaIndexes.append(
                [len(self.points)-1, self.poses[-1].theta])

        if len(self.poses) > 1:
            self.interpolateTheta(knownThetaIndexes)

    def drawPoints(self, screen, m):

        POINT_SIZE = 1
        TANGENT_LENGTH = 10

        for p in self.points:
            p.px, p.py = m.inchToPixel(p.x, p.y)
            Utility.drawLine(screen, Utility.PURPLE, p.px, p.py, *Utility.vector(
                p.px, p.py, p.theta, TANGENT_LENGTH * m.getPartialZoom(0.5)),  m.getPartialZoom(0.75))

        for p in self.points:
            Utility.drawCircle(screen, p.px, p.py, p.color,
                               POINT_SIZE * m.getPartialZoom(0.75))

    def drawRobot(self, screen, m, pointIndex):

        if m.simulating:
            m.simulating = self.robot.simulationTick(screen, m, pointIndex)

    def drawPanel(self, screen, m):
        if m.simulating:
            self.robot.drawPanel(screen)

    def handleRobotSliders(self, m, slider):
        self.robot.handleSliders(m, slider)
