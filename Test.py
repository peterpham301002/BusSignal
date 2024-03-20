#-------------------------------------------------------------------------------
#  Get a screen catpure from DPO4000 series scope and save it to a file

# python        2.7         (http://www.python.org/)
# pyvisa        1.4         (http://pyvisa.sourceforge.net/)
# numpy         1.6.2       (http://numpy.scipy.org/)
# MatPlotLib    1.0.1       (http://matplotlib.sourceforge.net/)
# ni-visa driver and ni-visa runtime to communicate with device

#-------------------------------------------------------------------------------
from ast import Not
import requests
import numpy as np
import time
import pylab
import argparse
import threading
import oracledb 
import json
import sys
import tkinter as tk
from struct import unpack
import pyvisa as visa
from collections import defaultdict
from collections import Counter
from colorama import Fore, Back, Style, init

global_passed = True
status = None
result = None
barcode = None
rm = visa.ResourceManager()

# List available resources (instruments)
resources = rm.list_resources()
oracledb.init_oracle_client()
# Print the list of resources
print("Available resources:", resources)
print(rm.session)

def printColour(colour, text):
    init()
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


def setupInstrumentValue(channel, port, barcode, scope, temprs):
    try:
        scope.write(channel+':SCAle '+ temprs["VoltDiv"])
        scope.write(channel+':OFFset ' + str(abs(int(temprs["Offset"]))))
        scope.write('HORizontal:SCAle 0.0001')
        scope.write(channel+':BWLImit ON')  # Enable bandwidth limit for Channel 1
        scope.write(channel+':BWLImit:FREQuency ' + str(temprs["BWlimit"])) 
        time.sleep(3) 
        Volts, yzero, Time = getMeasurementInstrumentValue(channel, port, barcode,scope)
        return Volts, yzero, Time
    except IndexError:
        sys.exit(1)

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
        return Volts, yzero, Time
    except IndexError:
        sys.exit(1)

def getMeasurementSetupData(barcode, flag):
    try:
        api_url = 'http://fvn-s-web01:5000/api/MI/GetBusSignalSetup'
        partno = barcode.split("-")[0]
        params = {'flag': f"{flag}", 'partno': f"{partno}"}
        response = requests.get(api_url, params=params)
        if response.status_code == 200:
            posts = response.json()
            if posts:
                return posts
            else:
                return None
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(e)
        sys.exit(1)

def measure(channel, port, barcode, flag):
    global global_passed
    if barcode is not None: 
        try:
            result = getMeasurementSetupData(barcode, flag)
            if result is not None:
                scope = rm.open_resource(port) # Open port to connect to instrument
                scope.write("DATa:SOU " + channel) # Choose channel
                scope.write('DATA:WIDTH 1')
                scope.write('DATA:ENC RPB')
                channel_scale = scope.query(f'{channel}:SCAle?')
                channel_offset = scope.query(f'{channel}:OFFSet?')
                temprs = result
                if round(float(channel_scale.replace("\n",""))) != int(result["VoltDiv"]) or round(float(channel_offset.replace("\n","")))  != abs(int(result["Offset"])): 
                    Volts,yzero,Time = setupInstrumentValue(channel, port, barcode, scope, temprs)
                else:
                    Volts,yzero,Time = getMeasurementInstrumentValue(channel, port, barcode, scope)

                vmin = result["Vmin"]
                vmax = result["Vmax"]

                # Get Max and Min volts
                printColour("RED" if np.max(Volts) < vmin[0]["Max"] or np.max(Volts) > vmax[0]["Max"] else "GREEN" ,f"Max voltage: {round(np.max(Volts),2)}")
                printColour("RED" if np.min(Volts) < vmin[0]["Min"] or np.min(Volts) > vmax[0]["Min"] else "GREEN" ,f"Min voltage: {round(np.min(Volts),2)}")
                
                if(np.max(Volts) < vmin[0]["Max"] or np.max(Volts) > vmax[0]["Max"]) or (np.min(Volts) < vmin[0]["Min"] or np.min(Volts) > vmax[0]["Min"]):
                    status = 0 #fail
                else:
                    status = 1 #pass   
                blob = {f"{barcode}":[{"Vol Max":[{"Min Limit: ": vmin[0]["Max"]}, {"Value: ": round(np.max(Volts),2)}, {"Max Limit: ": vmax[0]["Max"]}]}, {"Vol Min":[{"Min Limit: ": vmin[0]["Min"]}, {"Value: ": round(np.min(Volts),2)}, {"Max Limit: ": vmax[0]["Min"]}]}]}
                updateValue(barcode, status, blob, flag)                           
                printColour("GREEN","VMax: "+f"{round(np.max(Volts),2)}"+ "-" +"VMin: "f"{round(np.min(Volts),2)}"+ "-"+"Status: " f"{status}")
                sys.exit("VMax: "+f"{round(np.max(Volts),2)}"+ "-" +"VMin: " + f"{round(np.min(Volts),2)}"+ "-"+"Status: " + f"{status}" )
            else:
                printColour("RED","Can not find data to setup instrument in this part!")
                sys.exit(1)
        except Exception as e:
            print(e)
            sys.exit(1)
    else:
        print(Fore.RED + "Barcode is null")
        sys.exit(1)
    print(Style.RESET_ALL)

def updateValue(barcode, status, blob, flag):
    try:
        api_url = ''
        partno = barcode.split("-")[0]
        order = barcode.split("-")[2]
        params = {'barcode': f"{barcode}", 'partno': f"{partno}", 'order': f"{order}", 'status': f"{status}", 'blod': json.dumps(blob).encode('utf-8'), 'flag': f"{flag}"}
        response = requests.post(api_url, params=params)
        if response.status_code == 200:
            posts = response.json()
            if posts:
                return posts
            else:
                print(response.text)
                return None
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            sys.exit(1)
    except Exception as e:
        print(e)
        sys.exit(1)
        
def getInstrument():
    port = ""
    active_channels = ""
    try:
        resources = rm.list_resources()
        if len(resources) == 0:
            printColour("RED","No instruments found.")
        else:
            printColour("GREEN","Available instruments:")
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
        sys.exit(1)
    return port, active_channels
   
if __name__ == "__main__": 
    port, channel = getInstrument()
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", help="The file to be upload", default=channel.replace("\n",""))
    parser.add_argument("--port", help="Filename override", default=port)
    parser.add_argument("--barcode", help="Barcode input", default=barcode)
    parser.add_argument("--flag", help="Flag", default="1")
    # flag = 0 NO_LOAD
    # flag = 1 LOAD
    # flag = 2 OVER_LOAD
    args = parser.parse_args()
    if port !='' and channel !='':
        try:
            measure(**args.__dict__)
        except:
            sys.exit(1)
    elif channel =='':
        printColour("RED", "No channel found")
        sys.exit(1)
        
class VolMeasure:
    def __init__(self):
        self.Value = []
    def addValue(self, v):
        self.Value.append(v)
class Measure:
    def __init__(self):
        self.VolMax = {}
        self.VolMin = {}
    def addObject(self, key, value):
        self.VolMax[key] = value
        self.VolMin[key] = value

