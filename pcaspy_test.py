#!/usr/bin/env python
import threading
import numpy

from pcaspy import Driver, SimpleServer, Severity

MAX_POINTS = 1000
FREQUENCY = 1000
AMPLITUDE = 1.0
NUM_DIVISIONS = 10
MIN_UPDATE_TIME = 0.01

prefix = 'MTEST:'
pvdb = {
    'Run': {'type': 'enum',
            'enums': ['STOP', 'RUN'],
            'states': [Severity.NO_ALARM, Severity.MINOR_ALARM]},
    'MaxPoints': {'type': 'int',
                  'value': MAX_POINTS},
    'UpdateTime': {'prec': 3, 'unit': 's', 'value': 1},
    'TimePerDivision': {'prec': 5, 'value': 0.001},
    'TriggerDelay': {'prec': 5, 'unit': 's', 'value': 0.0005},
    'VoltsPerDivision': {'prec': 3, 'value': 0.2},
    'VoltOffset': {'prec': 3, 'unit': 'V'},
    'NoiseAmplitude': {'prec': 3, 'value': 0.2},
    'Waveform': {'count': MAX_POINTS,
                 'prec': 5},
    'TimeBase': {'count': MAX_POINTS,
                 'prec': 5,
                 'value': numpy.arange(MAX_POINTS, dtype=float)
                          * NUM_DIVISIONS / (MAX_POINTS - 1)},
    'MinValue': {'prec': 4},
    'MaxValue': {'prec': 4},
    'MeanValue': {'prec': 4},
}


class myDriver(Driver):
    def __init__(self):
        Driver.__init__(self)
        self.eid = threading.Event()
        self.tid = threading.Thread(target=self.runSimScope)
        self.tid.setDaemon(True)
        self.tid.start()

    def write(self, reason, value):
        status = True
        # take proper actions
        if reason == 'UpdateTime':
            value = max(MIN_UPDATE_TIME, value)
        elif reason == 'Run':
            if not self.getParam('Run') and value == 1:
                self.eid.set()
                self.eid.clear()
        # store the values
        if status:
            self.setParam(reason, value)
        return status

    def runSimScope(self):
        # simulate scope waveform
        while True:
            run = self.getParam('Run')
            updateTime = self.getParam('UpdateTime')
            if run:
                self.eid.wait(updateTime)
            else:
                self.eid.wait()
            run = self.getParam('Run')
            if not run: continue
            # retrieve parameters
            noiseAmplitude = self.getParam('NoiseAmplitude')
            timePerDivision = self.getParam('TimePerDivision')
            voltsPerDivision = self.getParam('VoltsPerDivision')
            triggerDelay = self.getParam('TriggerDelay')
            voltOffset = self.getParam('VoltOffset')
            # calculate the data wave based on timeWave scale
            timeStart = triggerDelay
            timeStep = timePerDivision * NUM_DIVISIONS / MAX_POINTS
            timeWave = timeStart + numpy.arange(MAX_POINTS) * timeStep
            noise = noiseAmplitude * numpy.random.random(MAX_POINTS)
            data = AMPLITUDE * numpy.sin(timeWave * FREQUENCY * 2 * numpy.pi) + noise
            # calculate statistics
            self.setParam('MinValue', data.min())
            self.setParam('MaxValue', data.max())
            self.setParam('MeanValue', data.mean())
            # scale/offset
            yScale = 1.0 / voltsPerDivision
            data = NUM_DIVISIONS / 2.0 + yScale * (data + voltOffset)
            self.setParam('Waveform', data)
            # do updates so clients see the changes
            self.updatePVs()


if __name__ == '__main__':
    server = SimpleServer()
    server.createPV(prefix, pvdb)
    driver = myDriver()

    # process CA transactions
    while True:
        server.process(0.1)