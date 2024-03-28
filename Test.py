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
from gpiozero import Button
from collections import defaultdict
from collections import Counter
from colorama import Fore, Back, Style, init

led_green = 17
led_red = 27
button_pin = 22
no_load = 16
load = 20
over_load = 21
status = None
result = None
barcode = None

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(led_green, GPIO.OUT)
GPIO.setup(led_red, GPIO.OUT)
GPIO.setup(no_load, GPIO.OUT)
GPIO.setup(load, GPIO.OUT)
GPIO.setup(over_load, GPIO.OUT)

btn = Button(button_pin,pull_up=True)    # True: trigger low | False: trigger high

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
    elif colour == "YELLOW":     
        print(Fore.YELLOW + text)
    else:
        print(Fore.RESET, text)
    print(Fore.RESET)

def highest_duplicate(arr, yzero):    #get high and low voltages
    counts = Counter(arr)  
    greater_than = {key: value for key, value in counts.items() if key >= yzero and value > 1}
    less_than = {key: value for key, value in counts.items() if key < yzero and value > 1}   
    max_greater_than = max(greater_than.values()) if greater_than else 0
    max_less_than = max(less_than.values()) if less_than else 0  
    max_greater_than_elements = {key: value for key, value in greater_than.items() if value == max_greater_than}
    max_less_than_elements = {key: value for key, value in less_than.items() if value == max_less_than}   
    return max_greater_than_elements, max_less_than_elements

def setupInstrumentValue(channel, port, barcode, scope, temprs):    #setup value for oscilloscope
    try:
        scope.write(channel+':SCAle '+ temprs["VoltDiv"])
        scope.write(channel+':OFFset ' + str(abs(int(temprs["Offset"]))))
        scope.write('HORizontal:SCAle 0.00001')
        scope.write(channel+':BANdwidth ONEfifty')  # MDO and DPO 3000 series
        scope.write(channel+':BWLImit ON')    # DPO 4000 Series
        scope.write(channel+':BWLImit:FREQuency ' + str(temprs["BWlimit"]))    # DPO 4000 Series
        time.sleep(3) 
        Volts, yzero, Time = getMeasurementInstrumentValue(channel, port, barcode,scope)
        return Volts, yzero, Time
    except Exception as e:
        printColour("RED",e)

def getMeasurementInstrumentValue(channel, port, barcode, scope):    #get date from the oscilloscope
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

def getMeasurementSetupData(barcode, flag):    #get data oscilloscope setup saved in database (BUS_SIGNAL_SETUP)
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

def measure(channel, port, barcode):    #measure data and set pass/fail result
    excepts = None
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
                    scope.write("DATa:SOU " + channel)    # Choose channel
                    scope.write('DATA:WIDTH 1')
                    scope.write('DATa:ENC RPB')    # DPO4000 Series
                    scope.write('DATa:ENCdg RPBinary')    # DPO3000 and MDO3000 Series
                    channel_scale = scope.query(f'{channel}:SCAle?')
                    channel_offset = scope.query(f'{channel}:OFFSet?')
                    temprs = result
                    if round(float(channel_scale.replace("\n",""))) != int(result["VoltDiv"]) or round(float(channel_offset.replace("\n","")))  != abs(int(result["Offset"])): 
                        Volts,yzero,Time = setupInstrumentValue(channel, port, barcode, scope, temprs)
                    else:
                        Volts,yzero,Time = getMeasurementInstrumentValue(channel, port, barcode, scope)

                    vmin = result["Vmin"]
                    vmax = result["Vmax"]

                    if flag == '0': types = 'No load'
                    elif flag == '1': types = 'Load'
                    else: types = 'Over load'
                   
                    # Get Max and Min volts
                    print(types)
                    printColour("YELLOW" if np.max(Volts) < vmin["Max"] or np.max(Volts) > vmax["Max"] else "GREEN" ,f"Max voltage: {round(np.max(Volts),2)}")
                    printColour("YELLOW" if np.min(Volts) < vmin["Min"] or np.min(Volts) > vmax["Min"] else "GREEN" ,f"Min voltage: {round(np.min(Volts),2)}")
                                                          
                    blob.add_result_data(types, round(np.min(Volts),2), round(np.max(Volts),2)) 
                    
                    if(np.max(Volts) < vmin["Max"] or np.max(Volts) > vmax["Max"]) or (np.min(Volts) < vmin["Min"] or np.min(Volts) > vmax["Min"]):
                        status = '0' #fail                                                                     
                        break
                    else:
                        status = '1' #pass 
                        if flag == '0': 
                            GPIO.output(no_load, GPIO.LOW)
                            GPIO.output(load, GPIO.HIGH)
                            GPIO.output(over_load, GPIO.LOW)
                        elif flag == '1':
                            GPIO.output(no_load, GPIO.LOW)
                            GPIO.output(load, GPIO.LOW)
                            GPIO.output(over_load, GPIO.HIGH)   
                        else:
                            GPIO.output(over_load, GPIO.LOW) 
                            GPIO.output(no_load, GPIO.HIGH)
                            GPIO.output(load, GPIO.LOW)  
                        time.sleep(1)
                else:
                    printColour("RED","Can not find data to setup instrument in this part!")
                    break
        except Exception as e:
            excepts = e
            printColour("RED",e)
        
        if result is not None and excepts is None:
            blob.status = status
            if status == '1':
                GPIO.output(led_green, GPIO.HIGH)
            else:
                GPIO.output(led_red, GPIO.HIGH)
            blobstr = json.dumps(blob, default=lambda o: o.__dict__, indent=4)
            insertValue(blobstr)      
    else:
        print(Fore.RED + "Barcode is null")        
    print(Style.RESET_ALL)

def insertValue(data):    #insert data measured to database (DATA_BUS_SIGNAL)
    try:
        api_url = 'http://fvn-nb-063.friwo.local:8088/HomeAPI/InsertBusSignalData'  
        headers = {'Content-Type': 'application/json'}
        response = requests.post(api_url, data=data, headers=headers)
        if response.status_code == 200:         
            print(response.text)
        else:
            printColour("RED",f"Error: {response.status_code}"+ "\n" + f"{response.text}")        
    except Exception as e:
        printColour("RED",e)
        
def getInstrument():    #find oscilloscope and connect to it
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
        printColour("RED","An error occurred: " + e)
    return port, active_channels

def default_led():    #setup led and type to default
    GPIO.output(led_green, GPIO.LOW)
    GPIO.output(led_red, GPIO.LOW)
    GPIO.output(no_load, GPIO.HIGH)
    GPIO.output(load, GPIO.LOW)
    GPIO.output(over_load, GPIO.LOW)

def checkPreviousStation(barcode):    #check data in ICT station
    try:
        api_url = f'http://fvn-s-web01.friwo.local:5000/api/ProcessLock/FA/CheckPreviousStation/{barcode}/ICT'  
        response = requests.post(api_url)
        if response.status_code == 200 and response.text == '1':         
            return True
        else:
            return False         
    except Exception as e:
        return False

if __name__ == "__main__": 
    default_led()
    port, channel = getInstrument()
    while True:      
        try: 
            barcode = input("Barcode: ") 
            default_led()   # user scan barcode
            btn.wait_for_press()    # wait user press button    
            if checkPreviousStation(barcode) == True:
                if port !='' and channel !='':
                    try:
                        flag = '0' 
                        measure(channel.replace("\n",""),port,barcode)
                    except Exception as e:
                        print(e)
                elif channel =='':
                    printColour("RED", "No channel found")
            else:
                printColour("RED", "Fail previous station")
        except Exception as e:
            printColour("RED",e)