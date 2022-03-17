#!/usr/bin/python3
"""
draw_topology.py

Draws a topology read in the MiniNDN format.

22/12/2020        Andre Dexheimer Carneiro
"""
import sys
import logging
import matplotlib.pyplot as plt

from icnexperiment.topology_generation import Topology
from icnexperiment.dir_config import c_strLogDir

FONT_SIZE_NODE_NAME = 13
FONT_SIZE_AXIS_LABEL = 16
FONT_SIZE_AXIS_STEPS = 13
SHOULD_SHOW_APS = False

def main():

    log_file_path = c_strLogDir + 'draw_topology.log'
    try:
        logging.basicConfig(filename=log_file_path, format='%(asctime)s %(message)s', level=logging.INFO)
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    except Exception as e:
        print(f"[main] Exception raised while setting up logging: {e}")

    # Read input param
    if (len(sys.argv) == 1):
        logging.error('[main] No topology specified as first parameter!')
        exit()
    else:
        strTopoPath = sys.argv[1]

    logging.info('[main] Drawing topology from path=%s' % strTopoPath)
    pTopology = Topology.loadFromFile(strTopoPath)

    #################################################
    # Draw individual nodes
    lstHumanCoord   = []
    lstSensorCoord  = []
    lstDroneCoord   = []
    lstVehicleCoord = []
    for pNode in pTopology.lstNodes:
        if (pNode.getType() == 'human'):
            lstHumanCoord.append(pNode.getCoord())
        elif (pNode.getType() == 'sensor'):
            lstSensorCoord.append(pNode.getCoord())
        elif (pNode.getType() == 'drone'):
            lstDroneCoord.append(pNode.getCoord())
        elif (pNode.getType() == 'vehicle'):
            lstVehicleCoord.append(pNode.getCoord())

    # Draw points
    humanScatter = plt.scatter([x[0] for x in lstHumanCoord], [x[1] for x in lstHumanCoord], marker='*', s=200)
    sensorScatter = plt.scatter([x[0] for x in lstSensorCoord], [x[1] for x in lstSensorCoord], marker='x', s=200)
    droneScatter = plt.scatter([x[0] for x in lstDroneCoord], [x[1] for x in lstDroneCoord], marker='^', s=200)
    vehicleScatter = plt.scatter([x[0] for x in lstVehicleCoord], [x[1] for x in lstVehicleCoord], marker='s', s=200)

    # Draw hostnames
    for pNode in pTopology.lstNodes:
        plt.annotate(pNode.Name(), (pNode.nX, pNode.nY), xytext=(pNode.nX+800, pNode.nY+800), fontsize=FONT_SIZE_NODE_NAME)

    lstScatters = [humanScatter, sensorScatter, droneScatter, vehicleScatter]
    lstLabels = ['Soldier', 'Sensor', 'Drone', 'Vehicle']

    # Draw access points, if needed
    if SHOULD_SHOW_APS:
        lstAccessCoord = []
        for pAP in pTopology.lstAccessPoints:
            lstAccessCoord.append(pAP.getCoord())
        accessScatter = plt.scatter([x[0] for x in lstAccessCoord], [x[1] for x in lstAccessCoord], c='k', marker='.', s=120)
        if len(lstAccessCoord) > 0:
            lstScatters.append(accessScatter)
            lstLabels.append('Access Point')

    # Draw legend
    plt.legend(lstScatters, lstLabels, loc='lower left')

    # Set labels and font sizes
    plt.xlabel('Coordinate X (m)', fontsize=FONT_SIZE_AXIS_LABEL)
    plt.ylabel('Coordinate Y (m)', fontsize=FONT_SIZE_AXIS_LABEL)
    plt.xlim(0, 102000)
    plt.ylim(0, 102000)
    plt.tick_params(axis='both', which='major', labelsize=FONT_SIZE_AXIS_STEPS)

    #################################################
    # Draw links between nodes
    lstLinkCoords = []
    for pLink in pTopology.lstLinks:
        lstLinkCoords = []
        lstLinkCoords.append(pLink.origHost.getCoord())
        lstLinkCoords.append(pLink.destHost.getCoord())
        plt.plot([x[0] for x in lstLinkCoords], [x[1] for x in lstLinkCoords], linewidth=1.5, zorder=-1)

    ##################################################
    # Topology info
    logging.info('[main] Topology has links=%d; humans=%d; drones=%d; sensors=%d; vehicles=%d' % (len(pTopology.lstLinks), len(lstHumanCoord), len(lstDroneCoord), len(lstSensorCoord), len(lstVehicleCoord)))

    plt.show()
    logging.info('[main] Done! Log written to %s' % (log_file_path))

if __name__ == '__main__':
    main()