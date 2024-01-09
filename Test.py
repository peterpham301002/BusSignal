#-------------------------------------------------------------------------------
#  Get a screen catpure from DPO4000 series scope and save it to a file

# python        2.7         (http://www.python.org/)
# pyvisa        1.4         (http://pyvisa.sourceforge.net/)
# numpy         1.6.2       (http://numpy.scipy.org/)
# MatPlotLib    1.0.1       (http://matplotlib.sourceforge.net/)
# ni-visa driver and ni-visa runtime to communicate with device

#-------------------------------------------------------------------------------
import numpy as np
import time
import pylab
import argparse
import oracledb 
import json
from struct import unpack
import pyvisa as visa
from collections import defaultdict
from collections import Counter
from colorama import Fore, Back, Style

passed = True
status = None
rm = visa.ResourceManager()
print(rm.session)
connection = None
if connection == None:
    connection = oracledb.connect(
        user='Mdata',
        password='trace##2017',
        dsn='(DESCRIPTION =(ADDRESS = (PROTOCOL = TCP)(HOST = 10.100.10.90)(PORT = 1521)) (CONNECT_DATA = (SERVER = DEDICATED) (SERVICE_NAME = TMES)))'
    )
    print("Connected to Oracle Database")

def printColour(colour, text):
    if colour == "RED":
        print(Fore.RED + text)
    elif colour == "GREEN":     
        print(Fore.GREEN + text)
    else:
        print(Fore.RESET, text)
    print(Fore.RESET)

def highest_duplicate(arr, yzero):
    counts = Counter(arr)  
    greater_than = {key: value for key, value in counts.items() if key >= yzero and value > 1}
    less_than = {key: value for key, value in counts.items() if key < yzero and value > 1}   
    max_greater_than = max(greater_than.values()) if greater_than else 0
    max_less_than = max(less_than.values()) if less_than else 0  
    max_greater_than_elements = {key: value for key, value in greater_than.items() if value == max_greater_than}
    max_less_than_elements = {key: value for key, value in less_than.items() if value == max_less_than}   
    return max_greater_than_elements, max_less_than_elements

def measure(channel, port, barcode):
    if barcode is not None: 
        try:
            scope = rm.open_resource(port) # Open port to connect to instrument
            scope.write("DATa:SOU " + channel) # Choose channel
            scope.write('DATA:WIDTH 1')
            scope.write('DATA:ENC RPB')
            channel_scale = scope.query(f'{channel}:SCAle?')
            channel_offset = scope.query(f'{channel}:OFFSet?')
            if round(float(channel_scale.replace("\n",""))) != 2 or round(float(channel_offset.replace("\n","")))  != 30: 
                Volts,yzero = setupInstrumentValue(channel, port, barcode, scope)
            else:
                Volts,yzero = getMeasurementInstrumentValue(channel, port, barcode, scope)
            high= ""
            low = ""

            # Get the High and Low volts with 
            # High is the highest density of point above the 'yzero' this mean High is the element value from 'Volts' which have the most volt dupilcate value higher than 'yzero'
            # Low is the highest density of point below the 'yzero' this mean Low is the element value from 'Volts' which have the most volt dupilcate value lower than 'yzero'
            # If 'yzero' equal or less than Min volts then High - Low is the Max - Min volts value
            if yzero > round(np.min(Volts),1):
                greater_than_result, less_than_result = highest_duplicate(Volts, yzero)
                if greater_than_result:
                    for keyHigh, value in greater_than_result.items():high = keyHigh
                else:
                    high = np.max(Volts)
                if less_than_result:
                    for keyLow, value in less_than_result.items():low = keyLow
                else:
                    low = np.min(Volts)
                printColour("RED" if high < 28.8 or high > 31.2 else "GREEN" ,f"High voltage: {round(high,1)}")
                printColour("RED" if low < 23.42 or low > 25.38 else "GREEN" ,f"Low voltage: {round(low,1)}")
            else:
                passed = False
                high = np.max(Volts)
                low = np.min(Volts)
                printColour("RED" if np.max(Volts) < 32.64 or np.max(Volts) > 35.36 else "GREEN" ,f"High voltage: {round(np.max(Volts),1)}")
                printColour("RED" if np.min(Volts) < 23.23 or np.min(Volts) > 24.17 else "GREEN" ,f"Low voltage: {round(np.min(Volts),1)}")

            # Get Max and Min volts
            printColour("RED" if np.max(Volts) < 32.64 or np.max(Volts) > 35.36 else "GREEN" ,f"Max voltage: {round(np.max(Volts),1)}")
            printColour("RED" if np.min(Volts) < 23.23 or np.min(Volts) > 24.17 else "GREEN" ,f"Min voltage: {round(np.min(Volts),1)}")
            
            if passed == False or (np.max(Volts) < 32.64 or np.max(Volts)) or (np.min(Volts) < 23.23 or np.min(Volts)) or (high < 28.8 or high > 31.2) or (low < 23.42 or low > 25.38):
                status = 1
            else:
                status = 0    
            blob = {"Max":{np.max(Volts)}, "Min":np.min(Volts), "High": high, "Low": low}
            updateValue(barcode, status, blob)
            
            # Show Histogram x: Time - y: Volts
            # pylab.plot(Time, Volts)
            # pylab.show()
           
            return high, low, round(np.max(Volts),1), round(np.min(Volts),1)
        except IndexError:
            return "error", "error", "error", "error"
    else:
        print(Fore.RED + "Barcode is null")
    print(Style.RESET_ALL)

def getInstrument():
    port = ""
    active_channels = ""
    try:
        resources = rm.list_resources()
        if len(resources) == 0:
            print("No instruments found.")
        else:
            print("Available instruments:")
            for idx, res in enumerate(resources):
                port = res
                print(f"{idx + 1}: {res}")
            instrument_visa_address = resources[0]
            oscilloscope = rm.open_resource(instrument_visa_address)
            identification = oscilloscope.query('*IDN?')
            active_channels = oscilloscope.query('DATA:SOURCE?')
            print("Active Channels:", active_channels)
            print("Connected to:", identification)
            oscilloscope.close()
    except visa.VisaIOError as e:
        print("An error occurred:", e)
    return port, active_channels

def setupInstrumentValue(channel, port, barcode, scope):
    try:
        scope.write(channel+':SCAle 2')
        scope.write(channel+':OFFset 30')
        scope.write('HORizontal:SCAle 0.0001')
        scope.write(channel+':BWLImit ON')  # Enable bandwidth limit for Channel 1
        scope.write(channel+':BWLImit:FREQuency 200000000') 
        time.sleep(3) 
        Volts, yzero = getMeasurementInstrumentValue(channel, port, barcode,scope)
        return Volts, yzero
    except IndexError:
        return None

def getMeasurementInstrumentValue(channel, port, barcode, scope):
    try:
        ymult = float(scope.query('WFMPRE:YMULT?')) # y-axis least count
        yzero = float(scope.query('WFMPRE:YZERO?')) # y-axis zero error
        yoff = float(scope.query('WFMPRE:YOFF?')) # y-axis offset
        xincr = float(scope.query('WFMPRE:XINCR?')) # x-axis least count
        xdelay = float(scope.query('HORizontal:POSition?'))
        scope.write('CURVE?')
        data = scope.read_raw() # Reading binary data
        headerlen = 2 + int(data[1]) # Finding header length
        header = data[:headerlen] # Separating header 
        ADC_wave = data[headerlen:-1] # Separating data
        ADC_wave = np.array(unpack('%sB' % len(ADC_wave),ADC_wave))
        Volts = (ADC_wave - yoff) * ymult  + yzero
        Time = np.arange(0, xincr * len(Volts), xincr)
        return Volts, yzero
    except IndexError:
        return None,None

def updateValue(barcode, status, blob):
    cursor = connection.cursor()
    try:
        partno = barcode.split("-")[0]
        order = barcode.split("-")[2]
        # Define the output parameter as a string
        output_param = cursor.var(oracledb.STRING)
        # Call the stored procedure
        cursor.callproc('P_UPDATE_BUS_SIGNAL_VALUE', [barcode, partno, order, status, json.dumps(blob), output_param])
        # Get the value of the output parameter (assuming it returns a single string)
        output_value = output_param.getvalue()
        print("Output value:", output_value)
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    # while(True):
    # acquire(channel="CH1", port="USB::0x0699::0x0406::C040243::INSTR")   
    port, channel = getInstrument() #Get device port and its channel
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", help="The file to be upload", default=channel.replace("\n",""))
    parser.add_argument("--port", help="Filename override", default=port)
    parser.add_argument("--barcode", help="Barcode input", default="01960239-0000001-1009090-101")
    args = parser.parse_args()
    measure(**args.__dict__)
    
    