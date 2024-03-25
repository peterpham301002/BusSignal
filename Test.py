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
import argparse
import json
import sys
import tkinter as tk
from struct import unpack
import pyvisa as visa
import RPi.GPIO as GPIO
from collections import defaultdict
from collections import Counter
from colorama import Fore, Back, Style, init

led_green = 17
led_red = 27
return_no_load = 22
status = None
result = None
barcode = None

GPIO.setmode(GPIO.BCM)
GPIO.setup(led_green, GPIO.OUT)
GPIO.setup(led_red, GPIO.OUT)
GPIO.setup(return_no_load, GPIO.OUT)

rm = visa.ResourceManager()

class ResultData:
    def __init__(self, type, vmin, vmax):
        self.type = type
        self.vmin = vmin
        self.vmax = vmax

class BarcodeData:
    def __init__(self, barcode, order, resultdata=None):
        self.barcode = barcode
        self.order = order
        self.resultdata = resultdata if resultdata is not None else []
    def add_result_data(self, type, vmin, vmax):
        self.resultdata.append(ResultData(type, vmin, vmax))
    def status(self, status):
        self.status = status

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
        api_url = 'http://fvn-s-web01.friwo.local:5000/api/MI/GetBusSignalSetup'
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

def measure(channel, port, barcode):
    default_led()
    blob = BarcodeData('','','')
    status = '0'
    flags = ['0','1','2']
    if barcode is not None: 
        try:
            blob = BarcodeData(barcode, barcode.split("-")[2])
            for flag in flags:
                result = getMeasurementSetupData(barcode, flag)
                if result is not None:
                    types = None
                    try:
                        scope = rm.open_resource(port)# Open port to connect to instrument
                    except:
                         print("")
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
                    printColour("RED" if np.max(Volts) < vmin["Max"] or np.max(Volts) > vmax["Max"] else "GREEN" ,f"Max voltage: {round(np.max(Volts),2)}")
                    printColour("RED" if np.min(Volts) < vmin["Min"] or np.min(Volts) > vmax["Min"] else "GREEN" ,f"Min voltage: {round(np.min(Volts),2)}")
                    
                    if flag == '0': types = 'No load'
                    elif flag == '1': types = 'Load'
                    else: types = 'Over load'
                    
                    blob.add_result_data(types, round(np.min(Volts),2), round(np.max(Volts),2)) 
                    
                    if(np.max(Volts) < vmin["Max"] or np.max(Volts) > vmax["Max"]) or (np.min(Volts) < vmin["Min"] or np.min(Volts) > vmax["Min"]):
                        status = '0' #fail
                        break
                    else:
                        status = '1' #pass                                             
                    
                    printColour("GREEN","VMax: "+f"{round(np.max(Volts),2)}"+ "-" +"VMin: "f"{round(np.min(Volts),2)}"+ "-"+"Status: " f"{status}")
                else:
                    printColour("RED","Can not find data to setup instrument in this part!")
                    break
        except Exception as e:
            print(e)
        finally:
            blob.status = status
            if status == '1':
                GPIO.output(led_green, GPIO.HIGH)
                time.sleep(2)
            else:
                GPIO.output(led_red, GPIO.HIGH)
                time.sleep(2) 
            blobstr = json.dumps(blob, default=lambda o: o.__dict__, indent=4)
            updateValue(blobstr)       
    else:
        print(Fore.RED + "Barcode is null")        
    print(Style.RESET_ALL)

def updateValue(data):
    try:
        api_url = 'http://fvn-nb-063.friwo.local:8088/HomeAPI/InsertBusSignalData'  
        headers = {'Content-Type': 'application/json'}
        response = requests.post(api_url, data=data, headers=headers)
        if response.status_code == 200:         
            print(response.text)
        else:
            print(f"Error: {response.status_code}")
            print(response.text)          
    except Exception as e:
        print(e)
        
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

def default_led():
    GPIO.output(led_green, GPIO.LOW)
    GPIO.output(led_red, GPIO.LOW)
    GPIO.output(return_no_load, GPIO.HIGH)
    time.sleep(1)
    GPIO.output(return_no_load, GPIO.LOW)  

if __name__ == "__main__": 
    port, channel = getInstrument()
    parser = argparse.ArgumentParser()
    # parser.add_argument("--channel", help="The file to be upload", default=channel.replace("\n",""))
    # parser.add_argument("--port", help="Filename override", default=port)
    parser.add_argument("--barcode", help="Barcode input", default="01962072-0-0-0")
    # parser.add_argument("--flag", help="Flag", default="1")
    # flag = 0 NO_LOAD
    # flag = 1 LOAD
    # flag = 2 OVER_LOAD
    args = parser.parse_args()
    if port !='' and channel !='':
        try:
            # Send PIO to switch NO_LOAD state with flag = 0
            flag = '0' 
            measure(channel.replace("\n",""),port,**args.__dict__)
        except:
            sys.exit(1)
    elif channel =='':
        printColour("RED", "No channel found")
        # sys.exit(1)
        

