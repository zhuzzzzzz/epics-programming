
import pyvisa
 
rm = pyvisa.ResourceManager()
inst = rm.open_resource('TCPIP0::localhost::hislip_PXI0_CHASSIS1_SLOT1_INDEX0::INSTR')
inst.timeout = 20000
 
print(inst.query("*IDN?"))