#!/usr/bin/python
"""
This MiniNDN experiment instantiates consumers and producers based on the
packages and their timestamps created and queued by DataManager.

Created 25/09/2020 by Andre Dexheimer Carneiro
"""
import sys
import os
import time
import logging
import getopt
import psutil
import subprocess
from random   import randint
from datetime import datetime, timedelta

try:
   from minindn.minindn import Minindn
   from minindn.wifi.minindnwifi import MinindnWifi
   from minindn.util import MiniNDNCLI, MiniNDNWifiCLI, getPopen
   from minindn.apps.app_manager import AppManager
   from minindn.apps.nfd import Nfd
   from minindn.apps.nlsr import Nlsr
   from minindn.helpers.nfdc import Nfdc
   from mininet.node import RemoteController
   g_bMinindnLibsImported = True
except ImportError:
   print('Could not import MiniNDN libraries')
   g_bMinindnLibsImported = False

from icnexperiment.data_generation import DataManager, curDatetimeToFloat, readHostNamesFromTopoFile
from icnexperiment.dir_config import c_strLogDir, c_strTopologyDir

# ---------------------------------------- Constants
c_strAppName         = 'C2Data'
c_strLogFile         = c_strLogDir + 'experiment_send.log'
c_strTopologyFile    = c_strTopologyDir + 'default-topology.conf'

c_sConsumerCooldownSec = 0.0
c_nSleepThresholdMs    = 100
c_sExperimentTimeSec   = 250
c_nCacheSizeDefault    = 0

c_nNLSRSleepSec   = 40
c_strNLSRLogLevel = 'NONE'
c_strNFDLogLevel  = 'DEBUG'

g_bIsMockExperiment  = False
g_bExperimentModeSet = False
g_bSDNEnabled        = False
g_strNetworkType     = ''

g_dtLastProducerCheck     = None
g_nProducerCheckPeriodSec = 5
g_bShowMiniNDNCli         = True

logging.basicConfig(filename=c_strLogFile, format='%(asctime)s %(message)s', level=logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


# ---------------------------------------- RandomTalks
class RandomTalks():

   def __init__(self, lstHosts, lstDataQueue):
      """
      Constructor. Meh
      """
      self.logFile          = None
      self.pDataManager     = DataManager()
      self.lstHosts         = lstHosts
      self.strTTLValues     = 'None'
      self.strPayloadValues = 'None'
      self.lstDataQueue     = lstDataQueue
      self.nBytesConsumed   = 0
      self.hshConsumers     = {}
      self.strPayloadPath   = '/home/vagrant/mock_data'
      self.lstRunningPutChunks = []

   def setup(self):
      """
      Setup experiment
      """
      logging.info('[RandomTalks.setup] Setting up new experiment')
      self.nBytesConsumed = 0
      
      self.hshConsumers = {}
      for pHost in self.lstHosts:
         self.hshConsumers[str(pHost)] = datetime(1,1,1,0,0)

      # Get TTLs from data manager
      self.strTTLValues     = self.pDataManager.getTTLValuesParam()
      self.strPayloadValues = self.pDataManager.getPayloadValuesParam()

      # Create payload mock files
      DataManager.createPayloadFiles(self.lstDataQueue, self.strPayloadPath)

      # Get average payload size from DataManager. This will be used to set cache sizes in the future
      sPayloadAvg = self.pDataManager.avgPayloadSize()
      logging.info('[RandomTalks.setup] avgPayloadSize=%.3f' % sPayloadAvg)

      # Instantiate all producers
      # self.checkRunningProducers()

      # Log the current configuration for data_manager
      logging.debug('[RandomTalks.setup] Current data type configuration: \n%s' % self.pDataManager.info())
      logging.debug('[RandomTalks.setup] Note that this could be outdated since the data queue configuration is set when it is created!')

   def run(self):
      """
      Experiment routine. Returns tuple (dtBegin, dtEnd).
      """
      logging.info('[RandomTalks.run] Begin, maxExperimentTimeSec=%f' % c_sExperimentTimeSec)

      # Internal parameters
      dtBegin        = datetime.now()
      dtNow          = None
      dtDelta        = timedelta()
      nDataIndex     = 0
      sElapsedTimeMs = 0
      nIteration     = 0
      sTimeDiffSum   = 0
      sTimeDiffAvg   = 0
      while (((sElapsedTimeMs/1000) < c_sExperimentTimeSec) and (nDataIndex < len(self.lstDataQueue))):
         # Send data until the end of the experiment time
         # Sweep queue and send data according to the elapsed time
         dtNow      = datetime.now()
         dtDelta        = dtNow - dtBegin
         sElapsedTimeMs = dtDelta.microseconds/1000 + dtDelta.seconds*1000
         nIteration    += 1
         logging.debug('[RandomTalks.run] New iteration with sElapsedTimeMs=%s; dtDelta=%s' % (sElapsedTimeMs, str(dtDelta)))

         while (nDataIndex < len(self.lstDataQueue)) and (self.lstDataQueue[nDataIndex][0] <= sElapsedTimeMs):
            # Send data
            pDataBuff = self.lstDataQueue[nDataIndex]
            
            sTimeDiffMs   = sElapsedTimeMs - pDataBuff[0]
            sTimeDiffSum += sTimeDiffMs
            sTimeDiffAvg  = float(sTimeDiffSum)/(nDataIndex+1)
	    
            if (sTimeDiffMs > 5):
               logging.info('[RandomTalks.run] About to send data nDataIndex=%d/%d; elapsedSec=%s; timeDiffMs=%s, timeDiffAvg=%.2f, MBytesConsumed=%.3f' % (nDataIndex, len(self.lstDataQueue)-1, sElapsedTimeMs/1000.0, sTimeDiffMs, sTimeDiffAvg, self.nBytesConsumed/(1024.0*1024.0)))

            # Instantiate consumer and producer host associated in the data package
            pDataPackage = pDataBuff[1]
            pProducer = self.findHostByName(pDataPackage.strOrig)
            pConsumer = self.findHostByName(pDataPackage.strDest)

            # In some setups, producer hosts might be killed by the OS for an unknown reason
            # This makes sure producers are running correctly during the simulation
            # As of 03/2021 this is not happening anymore. Possibly because of the call to getPopen(pHost, strCmdConsumer) instead of pHost.cmd (??)
            # self.checkRunningProducers()
            if(not self.isProducerRunning(pDataPackage)):
               self.instantiateProducer(pProducer, pDataPackage)
               time.sleep(0.2)

            self.instantiateConsumer(pConsumer, pDataPackage)
            nDataIndex += 1

         if (nDataIndex < len(self.lstDataQueue)):
            logging.debug('[RandomTalks.run] Waiting to send next data package nDataIndex=%s; pDataBuff[0]=%s; sElapsedTimeMs=%s' %
               (nDataIndex, self.lstDataQueue[nDataIndex][0], sElapsedTimeMs))
         else:
            logging.info('[RandomTalks.run] No more data to send')

         # Wait until next data is ready, if past threshold
         if (nDataIndex < len(self.lstDataQueue)):
            nNextStopMs = self.lstDataQueue[nDataIndex][0] - sElapsedTimeMs
            if (nNextStopMs > c_nSleepThresholdMs):
               logging.info('[RandomTalks.run] Sleeping until next data nNextStopMs=%s; c_nSleepThresholdMs=%s' % (nNextStopMs, c_nSleepThresholdMs))
               time.sleep(nNextStopMs/1000.0)

      # Close log file
      logging.info('[RandomTalks.run] Experiment done in %s seconds log written to %s' % (sElapsedTimeMs/1000, c_strLogFile))
      return (dtBegin, datetime.now())
 
   def checkRunningProducers(self):
      """
      Checks for all producer processes periodicaly. The period is set by g_nProducerCheckPeriodSec.
      """
      global g_nProducerCheckPeriodSec, g_dtLastProducerCheck

      if (g_dtLastProducerCheck is None) or (g_dtLastProducerCheck + timedelta(seconds=g_nProducerCheckPeriodSec) <= datetime.now()):

         logging.info('[RandomTalks.checkRunningProducers] Started check')

         lstRunningProducers = []
         for proc in psutil.process_iter():
            try:
               # Exceptions can happen here as processes are spawned and killed concurrently
               if (proc.name() == 'producer'):
                  # Second parameter should be the interest filter
                  strHost = RandomTalks.getHostnameFromFilter(proc.cmdline()[1])
                  lstRunningProducers.append(strHost)
            except:
               pass
         
         logging.info('[RandomTalks.checkRunningProducers] Found %d running producer programs, missing=%d' % (len(lstRunningProducers), len(self.lstHosts)-len(lstRunningProducers)))

         if (g_dtLastProducerCheck is None) and (len(lstRunningProducers) > 0):
            logging.critical('[RandomTalks.checkRunningProducers] first producer check, found %d producers already running' % len(lstRunningProducers))
      
         for pHost in self.lstHosts:
            if (str(pHost) not in lstRunningProducers):
               logging.info('[RandomTalks.checkRunningProducers] instantiating missing producer=%s' % str(pHost))
               self.instantiateProducer(pHost)
      
         # Update last check time
         g_dtLastProducerCheck = datetime.now()

   def isProducerRunning(self, pDataPackage):
      strFilter = RandomTalks.getChunksFilter(pDataPackage.strOrig, pDataPackage.nType, pDataPackage.nID)
      if (strFilter in self.lstRunningPutChunks):
         return True
      else:
         return False

   def instantiateProducer(self, pHost, pDataPackage):
      """
      Issues MiniNDN commands to instantiate a producer
      """
      global g_bIsMockExperiment
      if (pHost):

         nTTL = self.pDataManager.getTTLForDataType(pDataPackage.nType)
         strFilter = RandomTalks.getChunksFilter(pDataPackage.strOrig, pDataPackage.nType, pDataPackage.nID)
         strFilePath = DataManager.nameForPayloadFile(pDataPackage.nPayloadSize, self.strPayloadPath)
         strCmd = 'ndnputchunks %s -f %d < %s' % (strFilter, nTTL, strFilePath)
         if (not g_bIsMockExperiment):
            getPopen(pHost, strCmd, shell=True)
         
         self.lstRunningPutChunks.append(strFilter)      
         logging.info('[RandomTalks.instantiateProducer] ProducerCmd: ' + strCmd)
      else:
         logging.critical('[RandomTalks.instantiateProducer] Producer is nil!')
      
   def instantiateConsumer(self, pHost, pDataPackage):
      """
      Issues MiniNDN commands to set up a consumer for a data package
      """
      global g_bIsMockExperiment
      if (pHost):
         # Consumer program usage: consumer <interest> <hostName> <payload> <timestamp>
         sSecSinceLast = (datetime.now() - self.hshConsumers[str(pHost)]).total_seconds()
         if (sSecSinceLast < c_sConsumerCooldownSec):
            logging.info('[RandomTalks.instantiateConsumer] Will wait seconds=%.2f' % (c_sConsumerCooldownSec - sSecSinceLast))
            time.sleep(c_sConsumerCooldownSec - sSecSinceLast)

         strInterest = RandomTalks.getChunksFilter(pDataPackage.strOrig, pDataPackage.nType, pDataPackage.nID)
         strCmd = 'ndncatchunks %s' % strInterest
         if (not g_bIsMockExperiment):
            getPopen(pHost, strCmd, shell=True)

         self.nBytesConsumed += pDataPackage.nPayloadSize        
         logging.info('[RandomTalks.instantiateConsumer] %s ConsumerCmd: %s' % (pHost.name, strCmd))
      else:
         logging.critical('[RandomTalks.instantiateConsumer] Host is nil! host=%s' % str(pHost))

   def findHostByName(self, strHostName):
      """
      Returns a host found in the host list.
      """
      pResultHost = None
      for pHost in self.lstHosts:
         if (str(pHost) == strHostName):
            pResultHost = pHost
      return pResultHost  

   @staticmethod
   def getFilterByHostname(strName):
      """
      Creates interest filter base on the producer`s name
      """
      # return '/' + c_strAppName + '/' + strName + '/'
      # return '/%s' % (strName)
      return '/ndn/%s-site/%s/' % (strName, strName)

   @staticmethod
   def getHostnameFromFilter(strInterestFilter):
      """
      Returns a hostname read from an interest filter
      """
      return strInterestFilter.split('/')[-2]

   @staticmethod
   def getChunksFilter(strProd, nType, nId):
      return '%sType%dId%d/' % (RandomTalks.getFilterByHostname(strProd), nType, nId)

# ---------------------------------------- MockHost
class MockHost():

   def __init__(self, strName):
      # Shit
      self.strName = strName
      self.name = strName
      self.params = {'params': {'homeDir': ''}}

   def __repr__(self):
      return self.strName

   def cmd(self, strLine):
      return 0
   
# ---------------------------------------- runMock
def runMock(strTopoPath, lstDataQueue):
   """
   Runs mock experiment. No cummunication with Mininet or MiniNDN
   """
   logging.info('[runMock] Running mock experiment')
   lstHostNames = readHostNamesFromTopoFile(strTopoPath)
   lstHosts = [MockHost(strName) for strName in lstHostNames]
   Experiment = RandomTalks(lstHosts, lstDataQueue)
   Experiment.setup()
   Experiment.run()

def setStationIPs(pStation, strIP):
   # pStation.setIP(strIP, intf='%s-wlan1' % str(pStation))
   try:
      pStation.setIP(strIP, intf='%s-eth0' % str(pStation))
      pStation.setIP(strIP, intf='%s-eth1' % str(pStation))
      pStation.setIP(strIP, intf='%s-eth2' % str(pStation))
      pStation.setIP(strIP, intf='%s-eth3' % str(pStation))
      pStation.setIP(strIP, intf='%s-eth4' % str(pStation))
      pStation.setIP(strIP, intf='%s-eth5' % str(pStation))
      pStation.setIP(strIP, intf='%s-eth6' % str(pStation))
   except:
      return

# ---------------------------------------- runExperiment
def runExperiment(strTopoPath, lstDataQueue, bWifi=True):
   """
   Runs the experiment using regular MiniNDN
   """
   global g_bShowMiniNDNCli, g_bSDNEnabled
   logging.info('[runExperiment] Running MiniNDN experiment')

   if (bWifi):
      MiniNDNClass = MinindnWifi
   else:
      MiniNDNClass = Minindn
   
   Minindn.cleanUp()
   Minindn.verifyDependencies()

   ######################################################
   # Start MiniNDN and set controller, if any
   if (g_bSDNEnabled):
      ndn = MiniNDNClass(topoFile=strTopoPath, controller=RemoteController)
   else:
      ndn = MiniNDNClass(topoFile=strTopoPath)
   
   ndn.start()

   # Wifi topology uses stations instead of hosts, the idea is the same
   if (bWifi):
      lstHosts = ndn.net.stations + ndn.net.hosts

      # for pStation in ndn.net.stations:
      #    strIP = pStation.IP() + '/24'
      #    setStationIPs(pStation, strIP)
      #    logging.info('[runExperiment] station=%s, IP=%s' % (str(pStation), strIP))

      if (ndn.net.aps is not None) and (len(ndn.net.aps) > 0):
         # Connect all APs to the remote controller
         # This should be done regardless of SDN, otherwise packets will not be routed
         logging.info('[runExperiment] Setting up access points...')
         nApId = 1
         for pAp in ndn.net.aps:
            strApId = '1000000000' + str(nApId).zfill(6)
            subprocess.call(['ovs-vsctl', 'set-controller', str(pAp), 'tcp:127.0.0.1:6633'])
            subprocess.call(['ovs-vsctl', 'set', 'bridge', str(pAp), 'other-config:datapath-id='+strApId])
            nApId += 1

            # TODO: Add priority based rules to APs if g_bSDNEnabled
            # ovs-ofctl add-flow <ap_name> dl_type=0x0800
   else:
      lstHosts = ndn.net.hosts

   #######################################################
   # Initialize NFD and set cache size based on host type
   logging.info('[runExperiment] Starting NFD on nodes')
   lstHumanHosts   = []
   lstDroneHosts   = []
   lstSensorHosts  = []
   lstVehicleHosts = []
   for pHost in lstHosts:
      if (pHost.name[0] == 'h'):
         lstHumanHosts.append(pHost)
      elif (pHost.name[0] == 'd'):
         lstDroneHosts.append(pHost)
      elif (pHost.name[0] == 's'):
         lstSensorHosts.append(pHost)
      elif (pHost.name[0] == 'v'):
         lstVehicleHosts.append(pHost)
      else:
         raise Exception('[runExperiment] Hostname=%s not recognized as human, drone, sensor or vehicle' % pHost.name)

   nfdsHuman = AppManager(ndn, lstHumanHosts, Nfd, csSize=c_nHumanCacheSize, logLevel=c_strNFDLogLevel)
   logging.info('[runExperiment] Cache set for humans=%d, size=%d' % (len(lstHumanHosts), c_nHumanCacheSize))
   nfdsDrone = AppManager(ndn, lstDroneHosts, Nfd, csSize=c_nDroneCacheSize, logLevel=c_strNFDLogLevel)
   logging.info('[runExperiment] Cache set for drones=%d, size=%d' % (len(lstDroneHosts), c_nDroneCacheSize))
   nfdsSensor = AppManager(ndn, lstSensorHosts, Nfd, csSize=c_nSensorCacheSize, logLevel=c_strNFDLogLevel)
   logging.info('[runExperiment] Cache set for sensors=%d, size=%d' % (len(lstSensorHosts), c_nSensorCacheSize))
   nfdsVehicle = AppManager(ndn, lstVehicleHosts, Nfd, csSize=c_nVehicleCacheSize, logLevel=c_strNFDLogLevel)
   logging.info('[runExperiment] Cache set for vehicles=%d, size=%d' % (len(lstVehicleHosts), c_nVehicleCacheSize))

   # Advertise faces
   logging.info('[runExperiment] Setting up faces for %d hosts' % len(lstHosts))
   for pHostOrig in lstHosts:
      for pHostDest in lstHosts:
         if (pHostDest != pHostOrig):
            logging.debug('[runExperiment] Register, pHostOrig=%s; pHostDest=%s' % (str(pHostOrig), str(pHostDest)))
            Nfdc.createFace(pHostOrig, pHostDest.IP())
            Nfdc.registerRoute(pHostOrig, RandomTalks.getFilterByHostname(str(pHostDest)), pHostDest.IP())

   if (not bWifi):
      ##########################################################
      # Initialize NLSR
      logging.info('[runExperiment] Starting NLSR on nodes')
      nlsrs = AppManager(ndn, lstHosts, Nlsr, logLevel=c_strNLSRLogLevel)

      ##########################################################
      # Wait for NLSR initialization, at least 30 seconds to be on the safe side
      logging.info('[runExperiment] NLSR sleep set to %d seconds' % c_nNLSRSleepSec)
      time.sleep(c_nNLSRSleepSec)

   ##########################################################
   # Set up and run experiment
   logging.info('[runExperiment] Begin experiment')
   Experiment = RandomTalks(lstHosts, lstDataQueue)
   try:
      logging.info('[runExperiment] Running pingall ...')
      # ndn.net.pingAll()
      logging.info('[runExperiment] Pingall done')
      Experiment.setup()
      (dtBegin, dtEnd) = Experiment.run()
   except Exception as e:
      logging.error('[runExperiment] An exception was raised during the experiment: %s' % str(e))
      raise

   logging.info('[runExperiment] End of experiment, TimeElapsed=%s; KBytesConsumed=%.2f' % (str(dtEnd-dtBegin), float(Experiment.nBytesConsumed)/1024))

   if (g_bShowMiniNDNCli):
      if (bWifi):
         MiniNDNWifiCLI(ndn.net)
      else:
         MiniNDNCLI(ndn.net)
   ndn.stop()

# ---------------------------------------- setICNCache
def setICNCache():
   """
   Sets cache for ICN hosts.
   """
   global c_nHumanCacheSize, c_nDroneCacheSize, c_nSensorCacheSize, c_nVehicleCacheSize
   c_nHumanCacheSize   = 80000
   c_nDroneCacheSize   = 60000
   c_nSensorCacheSize  = 40000
   c_nVehicleCacheSize = 100000
   logging.info('[setICNCache] Set, human=%d, drone=%d, sensor=%d, vehicle=%d' % (c_nHumanCacheSize, c_nDroneCacheSize, c_nSensorCacheSize, c_nVehicleCacheSize))

# ---------------------------------------- setIPCache
def setIPCache():
   """
   Sets cache for IP hosts.
   """
   global c_nHumanCacheSize, c_nDroneCacheSize, c_nSensorCacheSize, c_nVehicleCacheSize
   c_nHumanCacheSize   = 0
   c_nDroneCacheSize   = 0
   c_nSensorCacheSize  = 0
   c_nVehicleCacheSize = 0
   logging.info('[setIPCache] Set, human=%d, drone=%d, sensor=%d, vehicle=%d' % (c_nHumanCacheSize, c_nDroneCacheSize, c_nSensorCacheSize, c_nVehicleCacheSize))

# ---------------------------------------- setNetworkType
def setNetworkType(strMode):
   """
   Sets the network as 'sdn', 'icn' or 'ip'
   """
   global g_strNetworkType, g_bSDNEnabled
   if (g_strNetworkType == ''):
      if (strMode == 'sdn'):
         g_bSDNEnabled = True
         setICNCache()
      elif (strMode == 'icn'):
         g_bSDNEnabled = False
         setICNCache()
      elif (strMode == 'ip'):
         g_bSDNEnabled = False
         setIPCache()
      elif (strMode == 'ip_sdn'):
         g_bSDNEnabled = True
         setIPCache()
      else:
         raise Exception('[setNetworkType] Unrecognized network type=%s' % strMode)

      g_strNetworkType = strMode
      logging.info('[setNetworkType] Type=%s, RyuController=%s' % (g_strNetworkType, g_bSDNEnabled))
   else:
      raise Exception('[setNetworkType] called more than once, current type=%s' % g_strNetworkType)

# ---------------------------------------- showHelp
def showHelp():
   strHelp  =  'Help: -----------------------------------------------\n'
   strHelp += 'experiment_send.py - runs MiniNDN experiments with C2Data\n\n'
   strHelp += 'Usage:\n'
   strHelp += './experiment_send.py -t <topology_path> <options>\n'
   strHelp += 'Options can be, in any order:\n'
   strHelp += '  --mock:   Runs mock experiment, without any calls to Mininet, MiniNDN, NFD, NLSR, ...\n'
   strHelp += '  --sdn:    SDN experiment with Ryu controller\n'
   strHelp += '  --icn:    ICN experiment without specific controller\n'
   strHelp += '  --ip:     IP experiment, no specific controller or cache\n'
   strHelp += '  --ip_sdn: IP with SDN experiment, with Ryu controller and no cache\n'
   print(strHelp)

# ---------------------------------------- Main
def main():

   global g_bIsMockExperiment, g_strNetworkType, g_bMinindnLibsImported

   strMode = 'icn'
   strTopologyPath = ''
   short_options = 'hmt:'
   long_options  = ['help', 'mock', 'sdn', 'icn', 'ip', 'ip_sdn', 'topology=']
   opts, args = getopt.getopt(sys.argv[1:], short_options, long_options)
   for opt, arg in opts:
      if opt in ['-h', '--help']:
         showHelp()
         exit(0)
      elif opt in ('-t', '--topology'):
         strTopologyPath = arg
         logging.info('[main] Topology path=%s' % strTopologyPath)
      elif opt in ['-m', '--mock']:
         g_bIsMockExperiment = True
      elif opt == '--sdn':
         strMode = 'sdn'
      elif opt == '--icn':
         strMode = 'icn'
      elif opt == '--ip':
         strMode = 'ip'
      elif opt == '--ip_sdn':
         strMode = 'ip_sdn'

   setNetworkType(strMode)
   # Reset argv arguments for the minindn CLI
   sys.argv = [sys.argv[0]]

   # Check if topology was specified
   if (strTopologyPath == ''):
      logging.error('[main] No topology file specified!')
      showHelp()
      exit(0)
   
   # Load data queue
   lstDataQueue = DataManager.loadDataQueueFromTextFile(strTopologyPath)
   logging.info('[main] Data queue size=%d' % len(lstDataQueue))

   if (g_strNetworkType == ''):
      logging.error('[main] No network type set')
      showHelp()
      exit(0)

   if(g_bIsMockExperiment):
      runMock(strTopologyPath, lstDataQueue)
   else:
      if (g_bMinindnLibsImported):
         runExperiment(strTopologyPath, lstDataQueue, bWifi=False)
      else:
         logging.error('[main] Experiment can not run because MiniNDN libraries could not be imported')

if __name__ == '__main__':
   main()
