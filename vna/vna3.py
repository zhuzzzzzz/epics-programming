import pyvisa as visa
import matplotlib.pyplot as plt

# Change this variable to the address of your instrument
VISA_ADDRESS = 'TCPIP0::localhost::hislip_PXI0_CHASSIS1_SLOT1_INDEX0::INSTR'

# Create a connection (session) to the instrument
resourceManager = visa.ResourceManager()
session = resourceManager.open_resource(VISA_ADDRESS)

# # Command to preset the instrument and deletes the default trace, measurement, and window
# session.write("SYST:FPR")

# # Create and turn on window 1
# session.write("DISP:WIND1:STAT ON")

# # Create a S21 measurement
# session.write("CALC1:MEAS1:DEF 'S21'")

# # Displays measurement 1 in window 1 and assigns the next available trace number to the measurement
# session.write("DISP:MEAS1:FEED 1")

# # Set the active measurement to measurement 1
# session.write("CALC1:PAR:MNUM 1")

# # Set sweep type to linear
# session.write("SENS1:SWE:TYPE LIN")

# # Perfoms a single sweep
# session.write("SENS1:SWE:MODE SING")
# opcCode = session.query("*OPC?")

# # Get stimulus and formatted response data
# results = session.query_ascii_values("CALC1:MEAS1:DATA:FDATA?")
# xValues = session.query_ascii_values("CALC1:MEAS1:X:VAL?")

# plt.plot(xValues, results)
# plt.ylabel("dB")
# plt.xlabel("Frequency")
# plt.show()

#刷新次数
n=5
#曲线刷新等待时间
line_delay=1
#电机抖动等待时间
motor_delay=1

#曲线和点都取平均值

# Marker峰值
# 曲线峰值

# Get stimulus and formatted response data
results = session.query_ascii_values("CALC200:MEAS2:DATA:FDATA?")
xValues = session.query_ascii_values("CALC200:MEAS2:X:VAL?")
makerX1 = session.query_ascii_values("CALC:MEAS2:MARK1:X?")
makerY1 = session.query_ascii_values("CALC:MEAS2:MARK1:Y?")

print(makerX1, makerY1)

plt.plot(xValues, results)
plt.ylabel("dB")
plt.xlabel("Frequency")
plt.show()


